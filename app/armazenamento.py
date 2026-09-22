"""
armazenamento.py — Camada de PERSISTÊNCIA do histórico de conferências.

O motor (motor.py) confere guias e NÃO sabe onde o resultado é guardado. Toda a
persistência mora atrás da interface `Storage`. Hoje a implementação é SQLite (arquivo
em disco, stdlib, sem servidor, sem senha). Trocar para Postgres é escrever uma classe
`PostgresStorage(Storage)` com os mesmos métodos e mudar uma linha em `obter_storage()`.

O que é guardado: cada guia conferida pelo site (formulário, texto colado ou CSV), com a
decisão completa em JSON, a chave de duplicata (para a próxima guia igual ser pega) e
quando foi conferida. Os dados-fonte (guias.csv, regras_convenio.json) continuam sendo a
fonte de verdade em disco; isto é o rastro do que o sistema decidiu.

Só biblioteca padrão (sqlite3, json, datetime, abc).
"""

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class Storage(ABC):

    @abstractmethod
    def salvar_resultado(self, decisao: dict, origem: str = "app", lote: str = "") -> int:
        """Grava uma decisão. `lote` identifica a importação (arquivo + data). Devolve o id da linha."""

    @abstractmethod
    def listar_lotes(self) -> list:
        """As importações feitas: [{lote, nome, quando, origem, quantidade}], mais nova primeiro."""

    @abstractmethod
    def apagar_lotes(self, lotes: list) -> int:
        """Remove as guias das importações escolhidas. Devolve quantas linhas saíram."""

    @abstractmethod
    def listar(self, limite: int = 200) -> list:
        """Conferências mais recentes, mais nova primeiro."""

    @abstractmethod
    def resumo(self) -> dict:
        """Números agregados: total, ok, corrigir, nao_enviar, R$."""

    @abstractmethod
    def ids_com_chave(self, chave: list, excluir_id: str = "") -> list:
        """Ids de guias já conferidas com a mesma chave de duplicata."""

    @abstractmethod
    def listar_importadas(self) -> list:
        """A decisão mais recente de cada guia importada (uma por id_guia), mais nova primeiro."""

    @abstractmethod
    def apagar_tudo(self) -> int:
        """Limpa o histórico (ex.: conferências de teste). Devolve quantas linhas saíram."""


class SQLiteStorage(Storage):

    def __init__(self, arquivo: str):
        self.arquivo = arquivo
        os.makedirs(os.path.dirname(os.path.abspath(arquivo)), exist_ok=True)
        self._criar_schema()

    def _conectar(self):
        conn = sqlite3.connect(self.arquivo, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _criar_schema(self):
        with self._conectar() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conferencias (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    criado_em           TEXT NOT NULL,
                    id_guia             TEXT,
                    convenio            TEXT,
                    decisao             TEXT NOT NULL,   -- OK | CORRIGIR | NÃO ENVIAR
                    urgente             INTEGER NOT NULL DEFAULT 0,
                    valor_em_risco      REAL NOT NULL DEFAULT 0,
                    valor_reclassificar REAL NOT NULL DEFAULT 0,
                    chave_dup           TEXT,            -- JSON (lista) para achar cópias
                    decisao_json        TEXT NOT NULL,   -- a decisão completa
                    origem              TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chave ON conferencias(chave_dup)")
            colunas = {r[1] for r in conn.execute("PRAGMA table_info(conferencias)").fetchall()}
            if "lote" not in colunas:   # bancos criados antes desta coluna
                conn.execute("ALTER TABLE conferencias ADD COLUMN lote TEXT NOT NULL DEFAULT ''")
            conn.commit()

    def salvar_resultado(self, decisao: dict, origem: str = "app", lote: str = "") -> int:
        with self._conectar() as conn:
            cur = conn.execute(
                """
                INSERT INTO conferencias
                    (criado_em, id_guia, convenio, decisao, urgente, valor_em_risco,
                     valor_reclassificar, chave_dup, decisao_json, origem, lote)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    decisao.get("id_guia", ""),
                    decisao.get("convenio", ""),
                    decisao.get("decisao", ""),
                    1 if decisao.get("urgente") else 0,
                    float(decisao.get("valor_em_risco", 0.0) or 0.0),
                    float(decisao.get("valor_reclassificar", 0.0) or 0.0),
                    json.dumps(list(decisao.get("chave_duplicata", [])), ensure_ascii=False),
                    json.dumps(decisao, ensure_ascii=False, default=str),
                    origem,
                    lote,
                ),
            )
            conn.commit()
            return cur.lastrowid

    def listar(self, limite: int = 200) -> list:
        with self._conectar() as conn:
            linhas = conn.execute(
                "SELECT * FROM conferencias ORDER BY id DESC LIMIT ?", (limite,)
            ).fetchall()
        saida = []
        for l in linhas:
            d = json.loads(l["decisao_json"] or "{}")
            d.update({"id": l["id"], "criado_em": l["criado_em"], "origem": l["origem"]})
            saida.append(d)
        return saida

    def resumo(self) -> dict:
        with self._conectar() as conn:
            q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
            return {
                "total": q("SELECT COUNT(*) FROM conferencias"),
                "ok": q("SELECT COUNT(*) FROM conferencias WHERE decisao='OK'"),
                "corrigir": q("SELECT COUNT(*) FROM conferencias WHERE decisao='CORRIGIR'"),
                "nao_enviar": q("SELECT COUNT(*) FROM conferencias WHERE decisao='NÃO ENVIAR'"),
                "valor_em_risco_total": round(q("SELECT COALESCE(SUM(valor_em_risco),0) FROM conferencias") or 0.0, 2),
                "valor_reclassificar_total": round(q("SELECT COALESCE(SUM(valor_reclassificar),0) FROM conferencias") or 0.0, 2),
            }

    def ids_com_chave(self, chave: list, excluir_id: str = "") -> list:
        # Só carteirinha + data preenchidas identificam alguém (mesma regra do lote).
        if not chave or len(chave) < 3 or not chave[0] or not chave[2]:
            return []
        with self._conectar() as conn:
            linhas = conn.execute(
                "SELECT DISTINCT id_guia FROM conferencias WHERE chave_dup = ? AND id_guia <> ?",
                (json.dumps(list(chave), ensure_ascii=False), excluir_id),
            ).fetchall()
        return [l["id_guia"] for l in linhas if l["id_guia"]]


    def listar_lotes(self) -> list:
        with self._conectar() as conn:
            linhas = conn.execute(
                "SELECT lote, origem, MIN(criado_em) AS quando, COUNT(*) AS quantidade "
                "FROM conferencias GROUP BY lote, origem ORDER BY lote DESC"
            ).fetchall()
        saida = []
        for l in linhas:
            nome = l["lote"].split("|", 1)[1] if "|" in (l["lote"] or "") else (l["lote"] or "(sem nome)")
            saida.append({"lote": l["lote"], "nome": nome, "quando": l["quando"],
                          "origem": l["origem"], "quantidade": l["quantidade"]})
        return saida

    def apagar_lotes(self, lotes: list) -> int:
        if not lotes:
            return 0
        with self._conectar() as conn:
            marcas = ",".join("?" for _ in lotes)
            n = conn.execute(f"SELECT COUNT(*) FROM conferencias WHERE lote IN ({marcas})", list(lotes)).fetchone()[0]
            conn.execute(f"DELETE FROM conferencias WHERE lote IN ({marcas})", list(lotes))
            conn.commit()
        return n

    def listar_importadas(self) -> list:
        with self._conectar() as conn:
            linhas = conn.execute(
                "SELECT * FROM conferencias WHERE id IN (SELECT MAX(id) FROM conferencias GROUP BY id_guia) "
                "ORDER BY id DESC"
            ).fetchall()
        saida = []
        for l in linhas:
            d = json.loads(l["decisao_json"] or "{}")
            d.update({"id": l["id"], "criado_em": l["criado_em"], "origem": l["origem"], "lote": l["lote"]})
            saida.append(d)
        return saida

    def apagar_tudo(self) -> int:
        with self._conectar() as conn:
            n = conn.execute("SELECT COUNT(*) FROM conferencias").fetchone()[0]
            conn.execute("DELETE FROM conferencias")
            conn.commit()
        return n


_ARQUIVO_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dados_app", "historico.db"
)


def obter_storage(arquivo: str = None) -> Storage:
    """Devolve a implementação de Storage em uso. Hoje: SQLite. Caminho via VITALIS_DB."""
    return SQLiteStorage(arquivo or os.environ.get("VITALIS_DB") or _ARQUIVO_PADRAO)
