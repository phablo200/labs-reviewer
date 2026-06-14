from pydantic import BaseModel, Field


class LabCodeExampleRequest(BaseModel):
    """Input context used to extract repository-grounded code examples."""

    notes_context: str = Field(
        ...,
        description="Raw sketch notes plus any enriched repository context.",
    )
    repositories: list[str] = Field(
        default_factory=list,
        description="Normalized repositories in owner/repo format.",
    )
    max_examples: int = Field(
        default=3,
        ge=1,
        le=5,
        description="Maximum number of examples to return.",
    )


class LabCodeExampleItem(BaseModel):
    """A single repository-backed code example."""

    repository: str = Field(
        ...,
        min_length=1,
        description="Repository identifier in owner/repo format copied from the provided repository context.",
    )
    file_path: str = Field(
        ...,
        min_length=1,
        description="Exact path from a provided File section containing the snippet.",
    )
    language: str = Field(
        ...,
        min_length=1,
        description="Detected language for the snippet, based on the file path or File section language.",
    )
    snippet: str = Field(
        ...,
        min_length=1,
        description="Concrete code excerpt copied from the provided File section; do not summarize.",
    )
    why_it_matters: str = Field(
        ...,
        min_length=1,
        description="Why this exact snippet helps explain the technical lab.",
    )
    integration_hint: str = Field(
        ...,
        min_length=1,
        description="How the writer should integrate this exact snippet into the post narrative.",
    )


class LabCodeExampleResponse(BaseModel):
    """Structured response for extracted code examples."""

    examples: list[LabCodeExampleItem] = Field(
        default_factory=list,
        description="Concrete repository-backed examples. Use an empty list only when no File sections with code are available.",
    )
    summary: str = Field(
        default="",
        description="High-level summary of suggested examples.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings encountered during extraction.",
    )
