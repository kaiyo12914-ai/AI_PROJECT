import os
from git import Repo, GitCommandError
import zipfile
import shutil

def get_uncommitted_files(repo_dir):
    repo = Repo(repo_dir)
    untracked_files = repo.untracked_files
    modified_files = [item.a_path for item in repo.index.diff(None)]
    return untracked_files + modified_files

def zip_files(files, repo_dir, output_zip):
    with zipfile.ZipFile(output_zip, 'w') as zipf:
        for file in files:
            file_path = os.path.join(repo_dir, file)
            zipf.write(file_path, arcname=file)

def main():
    repo_dir = 'D:\\AI\\AI_TOOLS'
    output_zip = 'uncommitted_files.zip'

    uncommitted_files = get_uncommitted_files(repo_dir)
    zip_files(uncommitted_files, repo_dir, output_zip)

if __name__ == "__main__":
    main()