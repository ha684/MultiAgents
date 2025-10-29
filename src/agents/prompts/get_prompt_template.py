from typing import Optional
import yaml


def load_prompt_template(
    task_name: str = "text_generation",
    language_code: str = "en",
    variables: Optional[dict] = None,
):
    """
    Load a specific prompt template from a YAML file based on the given task name,
    and optionally format it with provided variables.

    :param task_name: The name of the task to determine which YAML file to load (e.g., 'summarization', 'translation').
    :param language_code: The language code to specify which prompt variant to load (e.g., 'en' for English).
    :param variables: An optional dictionary of values to format into the prompt template.
    :return: The formatted prompt string.
    """

    file_path = (
        f"src/agents/prompts/{task_name.lower()}.yaml"  # Adjust the path if needed
    )
    prompt_item = f"prompt_{language_code}"
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        if prompt_item not in data:
            raise KeyError(f"Item {prompt_item} not found in {task_name}.yaml")
        prompt: str = data[prompt_item]

        # Replace placeholders with actual values
        if variables:
            prompt = prompt.format(**variables)

        return prompt

    except FileNotFoundError:
        raise FileNotFoundError(f"File {file_path} not found.")
    except KeyError as e:
        raise KeyError(str(e))
    except Exception as e:
        raise RuntimeError(f"Error loading YAML: {str(e)}")
