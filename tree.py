import os

def generate_tree(startpath, output_file, ignore_dirs=None, ignore_exts=None, indent_char='|   ', prefix_branch='├── ', prefix_leaf='└── '):
    """
    Generates a directory tree structure and writes it to a file.

    Args:
        startpath (str): The path to the root directory of the project.
        output_file (str): The path to the output .txt file.
        ignore_dirs (list, optional): A list of directory names to ignore. Defaults to None.
        ignore_exts (list, optional): A list of file extensions to ignore (e.g., ['.pyc', '.log']). Defaults to None.
        indent_char (str, optional): Character(s) used for indentation. Defaults to '|   '.
        prefix_branch (str, optional): Prefix for directory entries. Defaults to '├── '.
        prefix_leaf (str, optional): Prefix for file entries that are the last in a directory. Defaults to '└── '.
    """
    if ignore_dirs is None:
        ignore_dirs = []
    if ignore_exts is None:
        ignore_exts = []

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"{os.path.basename(os.path.abspath(startpath))}/\n") # Write the root directory name

        # Internal recursive function to build the tree
        def _generate_level(current_path, prefix=""):
            # Get list of items in the current directory
            try:
                items = sorted(os.listdir(current_path))
            except PermissionError:
                f.write(f"{prefix}{prefix_leaf}[Error: Permission Denied to access {os.path.basename(current_path)}]\n")
                return
            except FileNotFoundError:
                f.write(f"{prefix}{prefix_leaf}[Error: Directory not found: {os.path.basename(current_path)}]\n")
                return

            # Filter out ignored directories and files
            filtered_items = []
            for name in items:
                item_path = os.path.join(current_path, name)
                if os.path.isdir(item_path):
                    if name not in ignore_dirs:
                        filtered_items.append(name)
                else: # It's a file
                    if not any(name.endswith(ext) for ext in ignore_exts):
                        filtered_items.append(name)
            
            items = filtered_items # Use the filtered list

            for i, name in enumerate(items):
                item_path = os.path.join(current_path, name)
                is_last = (i == len(items) - 1)
                
                connector = prefix_leaf if is_last else prefix_branch
                f.write(f"{prefix}{connector}{name}\n")

                if os.path.isdir(item_path):
                    new_prefix = prefix + (indent_char if not is_last else '    ') # Adjust indent for next level
                    _generate_level(item_path, new_prefix)

        _generate_level(startpath)
    print(f"Directory tree saved to {output_file}")

if __name__ == "__main__":
    # --- Configuration ---
    project_directory = "."  # Default: current directory. Change to your project's root path.
    # Example: project_directory = "/path/to/your/project" 
    
    output_filename = "project_tree.txt" # Name of the output file

    # Directories to ignore (add more as needed)
    directories_to_ignore = [
        ".git", 
        "__pycache__", 
        ".vscode", 
        ".idea", 
        "node_modules", 
        "venv", 
        "env",
        "build",
        "dist"
    ]
    
    # File extensions to ignore (add more as needed)
    extensions_to_ignore = [
        ".pyc", 
        ".pyo", 
        ".pyd", 
        ".log", 
        ".tmp", 
        ".swp", 
        ".DS_Store" # macOS specific
    ]
    # --- End Configuration ---

    # Ensure the project directory exists
    if not os.path.isdir(project_directory):
        print(f"Error: The specified project directory '{project_directory}' does not exist.")
    else:
        # Generate the tree
        generate_tree(
            startpath=project_directory, 
            output_file=output_filename,
            ignore_dirs=directories_to_ignore,
            ignore_exts=extensions_to_ignore
        )
