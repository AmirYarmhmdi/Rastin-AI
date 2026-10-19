"""File guide.

- Use: Contains unit tests for document processing skill behavior.
- Usage: Run this file with pytest when checking related behavior.
- Duties: Builds test data, calls the public API, and checks expected results.
- Depends on: Project modules: rastin_ai.skills,
  rastin_ai.skills.document_processing, and rastin_ai.skills.registry.
"""

import pytest

from rastin_ai.skills import SkillMetadata, SkillRegistry
from rastin_ai.skills.document_processing import DocumentProcessingSkill
from rastin_ai.skills.registry import DuplicateCapabilityError, DuplicateSkillError


def test_skill_metadata_can_be_created() -> None:
    metadata = SkillMetadata(
        name="example",
        description="An example skill.",
        version="0.1.0",
    )

    assert metadata.name == "example"
    assert metadata.description == "An example skill."
    assert metadata.version == "0.1.0"


def test_document_processing_skill_has_metadata_and_instructions() -> None:
    skill = DocumentProcessingSkill()

    assert skill.metadata.name == "document_processing"
    assert skill.metadata.description == (
        "Deterministic processing for supported document files."
    )
    assert skill.metadata.version == "0.1.0"
    assert "deterministic processing" in skill.instructions


def test_document_processing_skill_declares_planned_capabilities() -> None:
    skill = DocumentProcessingSkill()

    assert skill.capabilities == (
        "document.read.pdf",
        "document.read.excel",
        "document.read.excel.workbook",
        "document.read.excel.sheet",
        "document.read.csv",
        "document.read.text",
        "document.read.json",
        "document.read.docx",
    )


def test_document_processing_skill_exposes_pdf_as_executable_capability() -> None:
    skill = DocumentProcessingSkill()

    assert skill.executable_capabilities == (
        "document.read.pdf",
        "document.read.excel.workbook",
        "document.read.excel.sheet",
        "document.read.csv",
        "document.read.text",
        "document.read.json",
        "document.read.docx",
    )
    assert skill.get_tool("pdf_reader") is not None


def test_document_processing_skill_exposes_canonical_capability_definitions() -> None:
    skill = DocumentProcessingSkill()
    capabilities = {
        capability.name: capability for capability in skill.capability_definitions
    }

    pdf_capability = capabilities["document.read.pdf"]

    assert pdf_capability.description == (
        "Extract text and basic metadata from a local text-based PDF."
    )
    assert pdf_capability.input_schema.__name__ == "PDFReaderInput"


def test_document_processing_skill_keeps_high_level_excel_non_executable() -> None:
    skill = DocumentProcessingSkill()

    assert "document.read.excel" in skill.capabilities
    assert "document.read.excel.workbook" in skill.executable_capabilities
    assert "document.read.excel.sheet" in skill.executable_capabilities
    assert "document.read.csv" in skill.capabilities
    assert "document.read.text" in skill.capabilities
    assert "document.read.json" in skill.capabilities
    assert "document.read.docx" in skill.capabilities
    assert "document.read.excel" not in skill.executable_capabilities
    assert "document.read.csv" in skill.executable_capabilities
    assert "document.read.text" in skill.executable_capabilities
    assert "document.read.json" in skill.executable_capabilities
    assert "document.read.docx" in skill.executable_capabilities


def test_skill_registry_registers_and_retrieves_skill() -> None:
    registry = SkillRegistry()
    skill = DocumentProcessingSkill()

    registry.register(skill)

    assert registry.get("document_processing") is skill


def test_skill_registry_rejects_duplicate_skill_names() -> None:
    registry = SkillRegistry()
    registry.register(DocumentProcessingSkill())

    with pytest.raises(DuplicateSkillError, match="document_processing"):
        registry.register(DocumentProcessingSkill())


def test_skill_registry_lists_registered_skills() -> None:
    registry = SkillRegistry()
    skill = DocumentProcessingSkill()
    registry.register(skill)

    assert registry.list_skills() == (skill,)


def test_skill_registry_finds_skills_by_declared_capability() -> None:
    registry = SkillRegistry()
    skill = DocumentProcessingSkill()
    registry.register(skill)

    assert registry.find_by_capability("document.read.pdf") == (skill,)
    assert registry.find_by_capability("document.write.pdf") == ()


def test_skill_registry_lists_canonical_capabilities_for_prompting() -> None:
    registry = SkillRegistry()
    registry.register(DocumentProcessingSkill())

    prompt_views = registry.get_capability_prompt_views()
    pdf_view = next(view for view in prompt_views if view.name == "document.read.pdf")

    assert pdf_view.description == (
        "Extract text and basic metadata from a local text-based PDF."
    )
    assert "path" in pdf_view.input_schema["properties"]


def test_skill_registry_rejects_duplicate_capability_names() -> None:
    registry = SkillRegistry()
    registry.register(DocumentProcessingSkill())

    with pytest.raises(DuplicateCapabilityError, match="document.read.pdf"):
        registry.register_capability(
            DocumentProcessingSkill().capability_definitions[0]
        )
