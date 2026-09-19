# CodeLearn

CodeLearn is a web-based platform for teaching and learning programming. Teachers create courses, assignments, and quizzes; students write and submit code that gets graded automatically; and a small machine learning pipeline flags students who are struggling and recommends what might help them improve.

Built with **Django** and **scikit-learn**.

## Features

- **Role-based accounts** — Admin, Teacher, Student, and Parent, each with their own dashboard.
- **Automated code grading** — students submit code from the browser; it runs against test cases in an isolated sandbox and is scored automatically.
- **Quizzes and attendance tracking**.
- **Weak-topic detection** — a classifier flags students who are struggling with a topic, based on their quiz, assignment, coding, and attendance data.
- **Peer-based recommendations** — suggests lessons based on what helped similar students improve.
- **Plagiarism/similarity check** — flags suspiciously similar code submissions for teacher review.
- **Messaging, notifications, a calendar, and discussion forums**.
- **PDF report cards and completion certificates**.

## Tech Stack

- **Backend:** Django, Django REST Framework
- **Database:** MySQL (SQLite works out of the box for local development)
- **Machine Learning:** scikit-learn, pandas, numpy
- **PDFs:** ReportLab
- **Deployment:** Docker / Podman, Nginx

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Aayush-Parajuli-lab/Codelearn.git
cd Codelearn
```

### 2. Set up a virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run migrations

```bash
python manage.py migrate
```

> By default the project uses SQLite when `DEBUG=True`, so you don't need MySQL set up just to try it locally.

### 4. (Optional) Load demo data

This creates demo accounts (admin, teachers, students, parents) with realistic sample activity, so you have something to explore right away:

```bash
python manage.py demo_pipeline
```

### 5. Run the development server

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` in your browser.

### Demo login (if you ran `demo_pipeline`)

| Role    | Username   | Password   |
| ------- | ---------- | ---------- |
| Admin   | `admin1`   | `pass1234` |
| Teacher | `teacher1` | `pass1234` |
| Student | `student0` | `pass1234` |
| Parent  | `parent1`  | `pass1234` |

## Running with Docker / Podman

A full production-like setup (web app, database, isolated code-runner, Nginx) is provided via Compose:

```bash
cp .env.example .env      # fill in your own secret key and DB credentials
podman-compose up --build   # or: docker compose up --build
```

## Project Structure

```
codelearn/          # Django project settings
accounts/           # Users, roles, authentication
academics/          # Courses, topics, lessons, enrollment
assignments/        # Assignments, test cases, submissions
quizzes/             # Quizzes and attempts
attendance/          # Attendance tracking
ml_engine/           # Weak-topic classifier + peer recommender
code_runner/         # Sandboxed code execution + plagiarism check
messaging/           # Direct/group messaging
notifications/       # Notification center
campus/              # Dashboards, views, templates
```

## Testing

```bash
python manage.py test
```

## License

See [LICENSE](LICENSE) for details.
