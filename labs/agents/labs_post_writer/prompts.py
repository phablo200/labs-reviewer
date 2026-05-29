class LabPostWriterPrompt:
    """Prompt templates for lab writing and structuring."""

    @staticmethod
    def build_system_prompt() -> str:
        """Build the system prompt for transforming notes into a coherent lab."""
        return """You are an expert technical lab writer.

Your task is to read sketch notes and transform them into a clear, coherent, and useful technical lab.

Rules:
1. Use all relevant information from the provided context.
2. Use code provided to improve your writting.
3. Remove duplication, vague fragments, and disconnected notes.
4. Organize the lab with a logical flow (introduction, core sections, conclusion).
5. Return only the final lab content in Markdown.
6. Do not add commentary before or after the Markdown.
7. Use provided code examples for enchance your explanations.
"""

    @staticmethod
    def build_improvement_prompt(
        current_markdown: str,
        revised_post: str,
        errors_found: list[str],
        improvement_tips: list[str],
        next_revision_checklist: list[str],
    ) -> str:
        """Build the prompt for applying reviewer feedback to a draft."""
        return (
            "You are improving a blog post after editorial review.\n\n"
            "Apply all relevant corrections and suggestions while preserving the intent.\n\n"
            "If repository-based code examples exist, keep at least one concrete example "
            "and improve technical accuracy of the explanation.\n\n"
            "Current post:\n"
            f"{current_markdown}\n\n"
            "Editor revised version:\n"
            f"{revised_post}\n\n"
            "Errors found:\n"
            + "\n".join(f"- {item}" for item in errors_found)
            + "\n\nImprovement tips:\n"
            + "\n".join(f"- {item}" for item in improvement_tips)
            + "\n\nNext revision checklist:\n"
            + "\n".join(f"- {item}" for item in next_revision_checklist)
            + "\n\nReturn only the final improved post in Markdown."
        )
