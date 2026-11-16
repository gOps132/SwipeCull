<a id="readme-top"></a>

<div align="center">

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]

</div>

<!-- PROJECT HEADER -->
<br />
<div align="center">
  <h3 align="center">SwipeCull</h3>

  <p align="center">
    A fast, Tinder-style media culling web app for triaging cloud storage photos with swipe gestures, keyboard shortcuts, and instant space-recovery tracking.
    <br />
    <a href="https://github.com/gOps132/SwipeCull"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://github.com/gOps132/SwipeCull/issues/new?labels=bug">Report Bug</a>
    &middot;
    <a href="https://github.com/gOps132/SwipeCull/issues/new?labels=enhancement">Request Feature</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

SwipeCull turns tedious cloud folder cleanup into a fast, focused triage workflow. Load a folder session, inspect each photo full-screen with zoom controls, and swipe or press a key to keep or trash files while tracking estimated storage freed in real time.

Key features:
* **Swipe & Keyboard Triage**: Drag cards left/right or use `←` (Trash), `→` (Keep), and `⌘Z` / `Ctrl+Z` (Undo).
* **Session Management**: Switch between source folders in the sidebar, create new demo sessions from the UI (`+ New`), and view a completion summary card when finished.
* **Zoom Controls**: Inspect photo details from `100%` to `300%` with the bottom-left `+` / `−` controls.
* **Finalize & Clean**: Review trashed items and confirm cleanup to remove trashed records and update session stats.
* **Profile & Dark Mode**: Manage account details and toggle persistent Dark Mode (with live preview) in Settings.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

<div align="center">

[![Django][Django-badge]][Django-url]
[![Python][Python-badge]][Python-url]
[![TailwindCSS][Tailwind-badge]][Tailwind-url]
[![PostgreSQL][Postgres-badge]][Postgres-url]

</div>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

Follow these steps to run SwipeCull locally.

### Prerequisites

* Python 3.10+
* `pip` and `venv`

### Installation

1. Clone the repository
   ```sh
   git clone https://github.com/gOps132/SwipeCull.git
   cd SwipeCull
   ```
2. Create and activate a virtual environment
   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. Install Python dependencies
   ```sh
   pip install -r requirements.txt
   ```
4. Apply database migrations (leave `DATABASE_URL` unset for local SQLite, or configure PostgreSQL in `.env`)
   ```sh
   python manage.py migrate
   ```
5. Create a user (or register via `/register/`) and seed a demo session
   ```sh
   python manage.py createsuperuser
   python manage.py seed_demo --count 10
   ```
6. Start the development server
   ```sh
   python manage.py runserver
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE -->
## Usage

1. Sign in at `/login/` (or create an account at `/register/`).
2. Triage photos in the active session:
   - **Keep**: Click **Keep**, drag the card right, or press `→`.
   - **Trash**: Click **Trash**, drag the card left, or press `←`.
   - **Undo**: Click **Undo** or press `⌘Z` / `Ctrl+Z`.
   - **Zoom**: Use the bottom-left `−` / `+` controls to zoom up to `300%`.
3. Click **+ New** in the left sidebar to spin up a new sample session, or **Finalize & Clean** in the right sidebar to apply your trash decisions.
4. Visit **Settings** (`/settings/`) to toggle **Dark Mode**.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

- [x] Vertical-slice Django architecture (`login`, `register`, `home`, `profile`, `user_settings`)
- [x] Database-backed `CullSession`, `MediaFile`, and `SwipeDecision` workflow
- [x] Optimistic GPU-accelerated swipe animations and zoom controls
- [x] Persistent Dark Mode across authenticated pages
- [ ] Live Google Drive OAuth folder sync and remote trash execution

See the [open issues](https://github.com/gOps132/SwipeCull/issues) for a full list of proposed features and known issues.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

Contributions are welcome!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat: add AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

Project Link: [https://github.com/gOps132/SwipeCull](https://github.com/gOps132/SwipeCull)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) / [ReadMeTemplate](https://github.com/gOps132/ReadMeTemplate)
* [Django](https://www.djangoproject.com/)
* [Tailwind CSS](https://tailwindcss.com/)
* [Img Shields](https://shields.io)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/gOps132/SwipeCull.svg?style=for-the-badge
[contributors-url]: https://github.com/gOps132/SwipeCull/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/gOps132/SwipeCull.svg?style=for-the-badge
[forks-url]: https://github.com/gOps132/SwipeCull/network/members
[stars-shield]: https://img.shields.io/github/stars/gOps132/SwipeCull.svg?style=for-the-badge
[stars-url]: https://github.com/gOps132/SwipeCull/stargazers
[issues-shield]: https://img.shields.io/github/issues/gOps132/SwipeCull.svg?style=for-the-badge
[issues-url]: https://github.com/gOps132/SwipeCull/issues
[Django-badge]: https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white
[Django-url]: https://www.djangoproject.com/
[Python-badge]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[Tailwind-badge]: https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white
[Tailwind-url]: https://tailwindcss.com/
[Postgres-badge]: https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white
[Postgres-url]: https://www.postgresql.org/
