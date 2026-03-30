"""
calc_agent.py — Agent de calcul scientifique pour la vérification d'exercices.

Exécute du code Python dans un sous-processus isolé (sandbox).
Utilisé par exercise_verifier.py pour vérifier les calculs dans les exercices
trou et cas_pratique via un flow LLM en 2 étapes :
  1. Le LLM analyse l'exercice et génère du code Python de vérification
  2. Le code est exécuté → le résultat est réinjecté pour la décision finale
"""

import os
import re
import subprocess
import sys
import tempfile
from typing import Optional


SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "30"))


def run_sandboxed_code(code: str, timeout: Optional[int] = None) -> dict:
    """
    Exécute du code Python dans un sous-processus isolé.

    Args:
        code: Code Python à exécuter.
        timeout: Timeout en secondes (défaut: SANDBOX_TIMEOUT).

    Returns:
        {
            "success": bool,
            "output": str,      # stdout complet
            "result": str,      # valeur de la variable result/answer/res
            "error": str,       # stderr si erreur
        }
    """
    effective_timeout = timeout or SANDBOX_TIMEOUT

    wrapper_code = code + "\n\n"
    wrapper_code += (
        "# --- Extraction du résultat ---\n"
        "_result_vars = ['result', 'resultat', 'answer', 'reponse', 'res']\n"
        "for _var in _result_vars:\n"
        "    if _var in dir() or _var in globals():\n"
        "        _val = globals().get(_var) or locals().get(_var)\n"
        "        if _val is not None:\n"
        "            print(f'__RESULT__={_val}')\n"
        "            break\n"
    )

    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as tmp_file:
            tmp_file.write(wrapper_code)
            tmp_path = tmp_file.name

        try:
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True,
                timeout=effective_timeout,
                cwd=tempfile.gettempdir(),
            )

            stdout = proc.stdout
            stderr = proc.stderr

            if proc.returncode != 0:
                return {
                    "success": False,
                    "output": stdout,
                    "result": "",
                    "error": stderr[:500],
                }

            result_match = re.search(r'__RESULT__=(.+)', stdout)
            result_value = result_match.group(1).strip() if result_match else ""

            return {
                "success": True,
                "output": stdout,
                "result": result_value,
                "error": "",
            }

        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "result": "",
            "error": f"Timeout : le code a dépassé {effective_timeout}s.",
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "result": "",
            "error": f"Erreur sandbox : {str(e)}",
        }


def run_calc_agent(code: str, timeout: int = 30) -> dict:
    """
    Point d'entrée principal de l'agent de calcul.
    Alias de run_sandboxed_code avec interface simplifiée.
    """
    return run_sandboxed_code(code, timeout=timeout)
