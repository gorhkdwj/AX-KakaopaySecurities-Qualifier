"""Contract reference integrity checks for OpenBell Guard.

P4-02 requires the development source contract and the plugin-shipped
reference copy to stay byte-identical. This test intentionally uses only the
Python standard library.
"""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_CONTRACT = PROJECT_ROOT / "docs" / "openbell-guard-metrics-validation-contract.md"
REFERENCE_CONTRACT = (
    PROJECT_ROOT
    / "src"
    / "skills"
    / "openbell-guard"
    / "references"
    / "metrics-validation-contract.md"
)


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ContractReferenceTest(unittest.TestCase):
    def test_contract_files_exist(self) -> None:
        self.assertTrue(SOURCE_CONTRACT.exists(), SOURCE_CONTRACT)
        self.assertTrue(REFERENCE_CONTRACT.exists(), REFERENCE_CONTRACT)

    def test_reference_copy_matches_source_sha256(self) -> None:
        self.assertEqual(sha256_bytes(SOURCE_CONTRACT), sha256_bytes(REFERENCE_CONTRACT))

    def test_contract_version_is_1_0_0(self) -> None:
        text = REFERENCE_CONTRACT.read_text(encoding="utf-8")
        self.assertIn("contract_version", text)
        self.assertIn("1.0.0", text)


if __name__ == "__main__":
    unittest.main()
