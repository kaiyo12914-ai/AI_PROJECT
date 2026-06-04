from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from webapps.database import db_factory


def _reset_db_factory_cache() -> None:
    db_factory._DB_FACTORY_MD_CACHE.update({"path": "", "mtime": 0.0, "data": None})


def test_cim_oracle_profile_reads_existing_env_db_factory_names() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / ".env_DB_factory"
        cfg_path.write_text(
            "\n".join(
                [
                    "CIM_DB_MPC_ORA_HOST=10.29.136.112",
                    "CIM_DB_MPC_ORA_PORT=1521",
                    "CIM_DB_MPC_ORA_DB=cim_service",
                    "CIM_DB_MPC_ORA_USER=cim_user",
                    "CIM_DB_MPC_ORA_PASS=cim_pass",
                    "CIM_DB_MPC_ORA_CONNECT_TIMEOUT_SEC=7",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"DB_FACTORY_MD_PATH": str(cfg_path)}, clear=False):
            _reset_db_factory_cache()
            cfg = db_factory.load_db_config("oracle", profile="CIM_MPC")

            assert cfg.ora_host == "10.29.136.112"
            assert cfg.ora_port == 1521
            assert cfg.ora_service == "cim_service"
            assert cfg.ora_user == "cim_user"
            assert cfg.ora_pass == "cim_pass"
            assert db_factory._env_float_profile("CIM_MPC", "ORA_CONNECT_TIMEOUT_SEC", 8.0) == 7.0


def test_erp_oracle_profile_reads_existing_env_db_factory_names() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / ".env_DB_factory"
        cfg_path.write_text(
            "\n".join(
                [
                    "ERP_DB_MPC_HOST=10.29.136.113",
                    "ERP_DB_MPC_PORT=1522",
                    "ERP_DB_MPC_DB=erp_service",
                    "ERP_DB_MPC_USER=erp_user",
                    "ERP_DB_MPC_PASS=erp_pass",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"DB_FACTORY_MD_PATH": str(cfg_path)}, clear=False):
            _reset_db_factory_cache()
            cfg = db_factory.load_db_config("oracle", profile="ERP_MPC")

            assert cfg.ora_host == "10.29.136.113"
            assert cfg.ora_port == 1522
            assert cfg.ora_service == "erp_service"
            assert cfg.ora_user == "erp_user"
            assert cfg.ora_pass == "erp_pass"


def test_profile_without_db_kind_prefers_cim_then_erp_then_doc() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / ".env_DB_factory"
        cfg_path.write_text(
            "\n".join(
                [
                    "ERP_DB_MPC_HOST=10.29.136.113",
                    "ERP_DB_MPC_DB=erp_service",
                    "ERP_DB_MPC_USER=erp_user",
                    "ERP_DB_MPC_PASS=erp_pass",
                    "CIM_DB_MPC_ORA_HOST=10.29.136.112",
                    "CIM_DB_MPC_ORA_DB=cim_service",
                    "CIM_DB_MPC_ORA_USER=cim_user",
                    "CIM_DB_MPC_ORA_PASS=cim_pass",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"DB_FACTORY_MD_PATH": str(cfg_path)}, clear=False):
            _reset_db_factory_cache()
            cfg = db_factory.load_db_config("oracle", profile="MPC")

            assert cfg.ora_host == "10.29.136.112"
            assert cfg.ora_service == "cim_service"
            assert cfg.ora_user == "cim_user"
            assert cfg.ora_pass == "cim_pass"


def test_profile_resolution_keeps_doc_db_compatibility() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / ".env_DB_factory"
        cfg_path.write_text(
            "\n".join(
                [
                    "DOC_DB_205_ORA_HOST=10.20.30.40",
                    "DOC_DB_205_ORA_SERVICE_NAME=legacy_doc",
                    "DOC_DB_205_ORA_USER=doc_user",
                    "DOC_DB_205_ORA_PASS=doc_pass",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"DB_FACTORY_MD_PATH": str(cfg_path)}, clear=False):
            _reset_db_factory_cache()
            cfg = db_factory.load_db_config("oracle", profile="DOC_205")

            assert cfg.ora_host == "10.20.30.40"
            assert cfg.ora_service == "legacy_doc"
            assert cfg.ora_user == "doc_user"
            assert cfg.ora_pass == "doc_pass"
