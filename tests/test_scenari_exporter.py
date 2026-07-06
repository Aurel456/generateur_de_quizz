"""Tests pour export/scenari_exporter.py — export SCENARI (.quiz XML)."""

import io
import zipfile
from dataclasses import dataclass, field
from typing import Dict, List

from export import scenari_exporter as se

# lxml en priorité (l'env CI peut avoir un pyexpat cassé) ; repli sur ElementTree.
try:
    from lxml import etree as _ETREE

    def _fromstring(xml: str):
        return _ETREE.fromstring(xml.encode("utf-8"))
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as _ETREE

    def _fromstring(xml: str):
        return _ETREE.fromstring(xml)

NS = {
    "sc": "http://www.utc.fr/ics/scenari/v3/core",
    "ent": "scenari:ENT",
    "sp": "http://www.utc.fr/ics/scenari/v3/primitive",
}


@dataclass
class FakeQuestion:
    question: str = "Quelle application ?"
    choices: Dict[str, str] = field(default_factory=lambda: {"A": "PEGASE", "B": "ESCALE", "C": "HERCULE"})
    correct_answers: List[str] = field(default_factory=lambda: ["B"])
    explanation: str = "ESCALE sécurise les échanges."
    source_pages: List[int] = field(default_factory=lambda: [1])


@dataclass
class FakeQuiz:
    title: str = "Test Quiz"
    difficulty: str = "moyen"
    questions: list = field(default_factory=lambda: [FakeQuestion()])
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeExercise:
    statement: str = "Calculez 2+2"
    expected_answer: str = "4"
    steps: list = field(default_factory=list)
    correction: str = "Le résultat est 4."
    exercise_type: str = "calcul"
    blanks: list = field(default_factory=list)
    sub_questions: list = field(default_factory=list)
    pedagogical_comment: str = ""
    source_pages: List[int] = field(default_factory=lambda: [1])


def _parse(xml: str):
    """Parse l'item et retourne la racine (lève si mal formé)."""
    return _fromstring(xml)


# ─────────────────────────── QCM ────────────────────────────

def test_qcu_mcqsur_single_correct():
    q = FakeQuestion(correct_answers=["B"])
    xml = se.question_to_scenari(q)
    root = _parse(xml)
    mcq = root.find("ent:mcqSur", NS)
    assert mcq is not None
    sol = mcq.find("sc:solution", NS)
    # B est le 2e choix (A, B, C triés) → choice="2"
    assert sol.get("choice") == "2"


def test_qcm_mcqmurbool_multiple_correct():
    q = FakeQuestion(
        choices={"A": "un", "B": "deux"},
        correct_answers=["A", "B"],
    )
    xml = se.question_to_scenari(q)
    root = _parse(xml)
    mcq = root.find("ent:mcqMurBool", NS)
    assert mcq is not None
    checked = [c for c in mcq.findall("sc:choices/sc:choice", NS) if c.get("solution") == "checked"]
    assert len(checked) == 2
    assert mcq.find("sc:globalExplanation", NS) is not None


def test_xml_escaping():
    q = FakeQuestion(question="A < B & C ?", correct_answers=["A"])
    xml = se.question_to_scenari(q)
    assert "&lt;" in xml and "&amp;" in xml
    _parse(xml)  # bien formé


# ─────────────────────────── Exercices ──────────────────────

def test_trou_cloze_with_options():
    ex = FakeExercise(
        statement="Sens ___ ici.",
        exercise_type="trou",
        blanks=[{"position": 1, "answer": "contraire", "accepted_answers": ["opposé"]}],
    )
    xml = se.exercise_to_scenari(ex)
    root = _parse(xml)
    cloze = root.find("ent:cloze", NS)
    assert cloze is not None
    gap = cloze.find(".//sc:textLeaf", NS)
    assert gap is not None
    options = gap.findall(".//sp:option", NS)
    assert {o.text for o in options} == {"contraire", "opposé"}


def test_trou_cloze_free_text_when_no_variant():
    ex = FakeExercise(
        statement="Une rubrique ___.",
        exercise_type="trou",
        blanks=[{"position": 1, "answer": "débitée"}],
    )
    xml = se.exercise_to_scenari(ex)
    root = _parse(xml)
    gap = root.find(".//sc:textLeaf", NS)
    # Pas d'options (saisie libre), mais la bonne réponse reste dans le textLeaf
    assert gap.find(".//sp:options", NS) is None
    assert "débitée" in "".join(gap.itertext())


def test_cas_pratique_practquiz():
    ex = FakeExercise(
        statement="Un usager demande un rescrit.",
        exercise_type="cas_pratique",
        correction="Transmettre à la direction.",
        sub_questions=[{"question": "Quelle suite ?", "answer": "Transmettre sans délai."}],
    )
    xml = se.exercise_to_scenari(ex)
    root = _parse(xml)
    pract = root.find("ent:practQuiz", NS)
    assert pract is not None
    assert pract.find(".//sp:desc", NS) is not None
    assert pract.find(".//sp:sol", NS) is not None
    assert "Quelle suite" in xml
    assert "Transmettre sans délai" in xml


def test_calcul_maps_to_practquiz():
    ex = FakeExercise(exercise_type="calcul", expected_answer="42", steps=["a", "b"])
    xml = se.exercise_to_scenari(ex)
    root = _parse(xml)
    assert root.find("ent:practQuiz", NS) is not None
    assert "42" in xml


# ─────────────────────────── ZIP ────────────────────────────

def test_export_scenari_zip_bundles_all_items():
    quiz = FakeQuiz(questions=[FakeQuestion(), FakeQuestion(question="Autre ?")])
    exercises = [FakeExercise(exercise_type="calcul")]
    data = se.export_scenari_zip(quiz, exercises)
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    assert len(names) == 3
    assert all(n.endswith(".quiz") for n in names)
    # Chaque item est un XML bien formé avec la racine sc:item
    for n in names:
        root = _parse(zf.read(n).decode("utf-8"))
        assert root.tag == "{http://www.utc.fr/ics/scenari/v3/core}item"


def test_export_scenari_zip_unique_filenames():
    # Deux questions identiques → noms de fichiers dédupliqués
    quiz = FakeQuiz(questions=[FakeQuestion(), FakeQuestion()])
    data = se.export_scenari_zip(quiz, None)
    names = se.build_scenari_items(quiz, None)
    assert len({n for n, _ in names}) == 2


def test_empty_inputs_produce_empty_zip():
    data = se.export_scenari_zip(None, None)
    zf = zipfile.ZipFile(io.BytesIO(data))
    assert zf.namelist() == []
