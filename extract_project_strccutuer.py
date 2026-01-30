import os

OUTPUT_FILE = "structure.md"

# folders to ignore
IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build"
}

def write_tree(root_dir, file, prefix=""):
    entries = sorted(os.listdir(root_dir))
    entries = [e for e in entries if e not in IGNORE_DIRS]

    for i, entry in enumerate(entries):
        path = os.path.join(root_dir, entry)
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "

        file.write(f"{prefix}{connector}{entry}\n")

        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            write_tree(path, file, prefix + extension)

def main():
    root_dir = "C:\\Users\\Sravan\\Desktop"#os.getcwd()
    project_name = "dentc-frontend"#os.path.basename(root_dir)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f"# Project Structure: {project_name}\n\n")
        f.write("```\n")
        f.write(f"{project_name}\n")
        write_tree(root_dir, f)
        f.write("```\n")

    print(f"✅ Project structure saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
