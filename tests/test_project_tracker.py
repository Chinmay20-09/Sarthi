# test_project_tracker.py

from skills.project_tracker.main import GitHubProjectSkill


USERNAME = "Chinmay20-09"

# Leave as None for public repositories.
# If you want to access private repositories,
# replace None with your GitHub Personal Access Token.
TOKEN = None


def main():
    skill = GitHubProjectSkill(
        username=USERNAME,
        token=TOKEN,
    )

    while True:
        print("\n==============================")
        print(" GitHub Project Tracker Test ")
        print("==============================")
        print("1. Check GitHub")
        print("2. Sync Repositories")
        print("3. Project Status")
        print("4. Exit")

        choice = input("\nSelect: ").strip()

        if choice == "1":
            print("\n")
            print(skill.execute("check github"))

        elif choice == "2":
            print("\n")
            print(skill.execute("sync repositories"))

        elif choice == "3":
            print("\n")
            print(skill.execute("project status"))

        elif choice == "4":
            break

        else:
            print("Invalid option.")


if __name__ == "__main__":
    main()