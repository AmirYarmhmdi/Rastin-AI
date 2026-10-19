"""File guide.

- Use: Defines canonical capability metadata and prompt projections.
- Usage: Import CapabilityDefinition and CapabilityPromptView from
  rastin_ai.skills.capabilities.
- Duties: Provides the single source of truth for capability descriptions and
  input schemas.
- Depends on: External packages: pydantic and typing.
"""

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StrictStr


class CapabilityPromptView(BaseModel):
    """Serializable capability metadata for LLM prompt construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)
    input_schema: dict[str, Any] = Field(
        validation_alias=AliasChoices("input_schema", "argument_schema")
    )

    @property
    def argument_schema(self) -> dict[str, Any]:
        """Backward-compatible prompt-view alias for older tool callers."""
        return self.input_schema


class CapabilityDefinition(BaseModel):
    """Canonical metadata for an executable Rastin-AI capability."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid", frozen=True)

    name: StrictStr = Field(min_length=1)
    description: StrictStr = Field(min_length=1)
    input_schema: type[BaseModel]

    def to_prompt_view(self) -> CapabilityPromptView:
        return CapabilityPromptView(
            name=self.name,
            description=self.description,
            input_schema=self.input_schema.model_json_schema(),
        )
