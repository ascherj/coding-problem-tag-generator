import os
import json
import re

import inquirer
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

client = OpenAI()
_ = load_dotenv(find_dotenv()) # read local .env file

LEETCODE_PROBLEM_DIR = os.getenv("LEETCODE_PROBLEM_DIR")
PROCESSED_FILES_LOG = "processed_files.json"

class TagGenerator:

    def __init__(self, problem_directory) -> None:
        self.problem_directory = problem_directory
        self.topics = self._load_topics()
        self.problems = self._list_problems()
        self.processed_files = self._load_processed_files()
        self.selected_problem = None

    def _load_topics(self) -> list[str]:
        with open("topics.json", "r") as f:
            return json.load(f)

    def _list_problems(self) -> list[str]:
        return [problem for problem in os.listdir(self.problem_directory) if problem.endswith(".md")]

    def _load_processed_files(self) -> set:
        if os.path.exists(PROCESSED_FILES_LOG):
            with open(PROCESSED_FILES_LOG, "r") as f:
                return set(json.load(f))
        return set()

    def _save_processed_file(self, filename):
        self.processed_files.add(filename)
        with open(PROCESSED_FILES_LOG, "w") as f:
            json.dump(list(self.processed_files), f)

    def _select_problem(self, problems):
        unprocessed_problems = [p for p in problems if p not in self.processed_files]
        if not unprocessed_problems:
            print("All problems have been processed.")
            return

        questions = [
            inquirer.List(
                "problem",
                message="Which problem would you like to select?",
                choices=unprocessed_problems
            )
        ]

        answers = inquirer.prompt(questions)
        return answers["problem"]

    def _api_call(self, solution_code):
        system_message = (
            "You are interacting with a user looking to categorize, within the Obsidian note-taking application, solutions to coding problems such as those typically found on LeetCode. Generate tags to be used to categorize the solutions for the provided solution code. Output the tags, and your reasoning for choosing them, in JSON format. Do not reference the program language as a tag. "
            f"Use the following JSON array of tags to help with your categorization, but feel free to add tags not included in the array:\n{self.topics}"
        )

        messages = [
                {
                    "role": "system",
                    "content": system_message
                },
                {
                    "role": "user",
                    "content": solution_code
                }
            ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.3,
            max_tokens=256,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0,
            response_format={
                "type": "json_object"
            }
        )

        return response.choices[0].message.content



    def _update_frontmatter_tags(self, filepath, new_tags):
        with open(filepath, "r") as f:
            content = f.read()

        # Match the frontmatter using regular expression
        frontmatter_match = re.match(r"---(.*?)---", content, re.DOTALL)
        if frontmatter_match:
            frontmatter = frontmatter_match.group(1)

            # Match the tags section within the frontmatter
            tags_match = re.search(r"tags:\s*\[\s*\]\s*\n|tags:\s*\n((?:\s*-\s*[^\n]+\n)*)", frontmatter)

            if tags_match:
                if "[]" in tags_match.group(0):
                    # Handle the case where tags are an empty list `[]`
                    updated_tags_str = "\n".join([f"  - {tag}" for tag in sorted(new_tags)])
                    updated_frontmatter = frontmatter.replace("tags: []", f"tags:\n{updated_tags_str}")
                else:
                    # Extract the existing tags and convert them to a list
                    current_tags = tags_match.group(1).strip().split("\n")
                    current_tags = [tag.strip().strip('-').strip() for tag in current_tags if tag.strip()]
                    # Merge with new tags and remove duplicates
                    updated_tags = list(set(current_tags + new_tags))
                    # Reformat the tags to YAML list format
                    updated_tags_str = "\n".join([f"  - {tag}" for tag in sorted(updated_tags)])
                    # Replace the old tags with the updated tags
                    updated_frontmatter = re.sub(r"tags:\s*\n((?:\s*-\s*[^\n]+\n)*)", f"tags:\n{updated_tags_str}\n", frontmatter)
                content = content.replace(frontmatter, updated_frontmatter)
            else:
                # Check if the tags section is empty (i.e., tags: with no list items)
                empty_tags_match = re.search(r"tags:\s*\n", frontmatter)
                if empty_tags_match:
                    updated_tags_str = "\n".join([f"  - {tag}" for tag in sorted(new_tags)])
                    updated_frontmatter = frontmatter.replace("tags:\n", f"tags:\n{updated_tags_str}\n")
                    content = content.replace(frontmatter, updated_frontmatter)
                else:
                    # Add the tags section if it doesn't exist at all
                    updated_tags_str = "\n".join([f"  - {tag}" for tag in sorted(new_tags)])
                    updated_frontmatter = frontmatter + f'tags:\n{updated_tags_str}\n'
                    content = content.replace(frontmatter, updated_frontmatter)

            # Write the updated content back to the file
            with open(filepath, "w") as f:
                f.write(content)
        else:
            print("No frontmatter found")
            # Add frontmatter if it doesn't exist
            updated_tags_str = "\n".join([f"  - {tag}" for tag in sorted(new_tags)])
            updated_frontmatter = f"---\ntags:\n{updated_tags_str}\n---\n"
            content = updated_frontmatter + content
            with open(filepath, "w") as f:
                f.write(content)



    def get_tags_for_solution(self) -> dict:
        if self.problems:
            self.selected_problem = self._select_problem(self.problems)
            print(f"Selected problem: {self.selected_problem}")

            file_contents = None
            filepath = os.path.join(self.problem_directory, self.selected_problem)
            with open(filepath, "r") as f:
                print(f"Reading problem: {self.selected_problem}")
                file_contents = f.read()

            try:
                solution_code = file_contents.split("```python")[1]
                tags_json = self._api_call(solution_code)
                print(tags_json)
                tags = json.loads(tags_json).get("tags", [])
                tags = [tag.lower().replace(" ", "-") for tag in tags]
                self._update_frontmatter_tags(filepath, tags)
                self._save_processed_file(self.selected_problem)
                print(f"Updated tags for {self.selected_problem}: {tags}")
            except IndexError:
                print("No code block found in the file")


if __name__ == "__main__":
    tag_generator = TagGenerator(LEETCODE_PROBLEM_DIR)
    tag_generator.get_tags_for_solution()
