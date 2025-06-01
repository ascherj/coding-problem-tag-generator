import os
import json
import re

import inquirer
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

client = OpenAI()
load_dotenv(find_dotenv(), override=True)  # Force reload local .env file

LEETCODE_PROBLEM_DIR = os.getenv("LEETCODE_PROBLEM_DIR")
PROCESSED_FILES_LOG = "processed_files.json"
TOPICS_FILE = "topics.json"

class TagGenerator:

    def __init__(self, problem_directory) -> None:
        self.problem_directory = problem_directory
        self.topics = self._load_topics()
        self.problems = self._list_problems()
        self.processed_files = self._load_processed_files()
        self.selected_problem = None

    def _load_topics(self) -> list[str]:
        with open(TOPICS_FILE, "r") as f:
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

    def _select_processing_mode(self):
        """Select whether to process a single file or all files"""
        questions = [
            inquirer.List(
                "mode",
                message="What would you like to do?",
                choices=[
                    "Process single unprocessed file",
                    "Process all unprocessed files",
                    "Regenerate tags for all files (including processed ones)"
                ]
            )
        ]

        answers = inquirer.prompt(questions)
        return answers["mode"]

    def _api_call(self, solution_code):
        system_message = (
            "You are interacting with a user looking to categorize, within the Obsidian note-taking application, solutions to coding problems such as those typically found on LeetCode. Generate tags to be used to categorize the solutions for the provided solution code. Output the tags, and your reasoning for choosing each tag, in JSON format. Do not reference the program language as a tag. "
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
            model="gpt-4o",
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

    def _process_single_file(self, filename):
        """Process a single file and return success status"""
        try:
            filepath = os.path.join(self.problem_directory, filename)

            with open(filepath, "r") as f:
                file_contents = f.read()

            # Extract solution code from Python code blocks
            solution_code = ""
            code_blocks = re.findall(r"```python(.*?)```", file_contents, re.DOTALL)
            for block in code_blocks:
                solution_code += block.strip() + "\n"
            solution_code = solution_code.strip()

            if not solution_code:
                print(f"⚠️  No Python code block found in {filename}")
                return False

            print(f"🔄 Processing: {filename}")

            # Get tags from API
            tags_json = self._api_call(solution_code)
            print(f"📋 API Response: {tags_json}")  # Show the full response including reasoning

            tags_data = json.loads(tags_json)
            tags = tags_data.get("tags", [])
            tags = [tag.lower().replace(" ", "-") for tag in tags]

            # Update file and tracking
            self._update_frontmatter_tags(filepath, tags)
            self._save_processed_file(filename)
            self._update_topics_file(tags)

            print(f"✅ Updated tags for {filename}: {tags}")
            return True

        except Exception as e:
            print(f"❌ Error processing {filename}: {str(e)}")
            return False

    def process_all_files(self, regenerate=False):
        """Process all files, optionally regenerating already processed ones"""
        if regenerate:
            files_to_process = self.problems
            print(f"🚀 Regenerating tags for all {len(files_to_process)} files...")
        else:
            files_to_process = [p for p in self.problems if p not in self.processed_files]
            print(f"🚀 Processing {len(files_to_process)} unprocessed files...")

        if not files_to_process:
            print("✨ No files to process!")
            return

        successful = 0
        failed = 0

        for i, filename in enumerate(files_to_process, 1):
            print(f"\n📁 [{i}/{len(files_to_process)}] Processing {filename}")

            if self._process_single_file(filename):
                successful += 1
            else:
                failed += 1

        print(f"\n🎉 Bulk processing complete!")
        print(f"✅ Successfully processed: {successful}")
        print(f"❌ Failed: {failed}")
        print(f"📊 Total files: {len(files_to_process)}")

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

    def _update_topics_file(self, problem_tags):
        all_tags = list(set(self.topics + problem_tags))
        all_tags.sort()

        new_tags = [tag for tag in all_tags if tag not in self.topics]
        if new_tags:
            print(f"📝 Added {len(new_tags)} new tags to {TOPICS_FILE}: {new_tags}")

        # Update the instance variable so subsequent calls see the new tags
        self.topics = all_tags

        with open(TOPICS_FILE, "w") as f:
            try:
                json.dump(all_tags, f, indent=4)
            except Exception as e:
                print(f"Error updating topics file: {e}")

    def get_tags_for_solution(self) -> dict:
        if not self.problems:
            print("No problem files found!")
            return

        # Get processing mode from user
        mode = self._select_processing_mode()

        if mode == "Process single unprocessed file":
            # Original single file processing
            self.selected_problem = self._select_problem(self.problems)
            if self.selected_problem:
                self._process_single_file(self.selected_problem)

        elif mode == "Process all unprocessed files":
            # Process all unprocessed files
            self.process_all_files(regenerate=False)

        elif mode == "Regenerate tags for all files (including processed ones)":
            # Process all files, including already processed ones
            self.process_all_files(regenerate=True)


if __name__ == "__main__":
    tag_generator = TagGenerator(LEETCODE_PROBLEM_DIR)
    tag_generator.get_tags_for_solution()
