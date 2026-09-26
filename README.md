# StudyPLUS

StudyPLUS is a small learning app for School AI web search, programming quizzes, and online language sessions. It runs as a static site on GitHub Pages and uses SQLite in the browser.

## Open the app

Visit the GitHub Pages URL for this repository. To enable Pages, open **Settings → Pages**, choose **Deploy from a branch**, and select **main** and **/(root)**.

On first use, enter your email and create an owner password. Then sign in and add accounts from the login screen.

## Important: browser demo

SQLite is saved in IndexedDB on the current browser and device. Data does not sync between visitors or devices. Clearing browser site data removes it. Roles and passwords are for a demo only: a static site cannot securely enforce permissions or provide shared accounts. Do not use real/private information here.

## Features

- **School AI:** opens a Google search for a question or topic.
- **Programming Class:** create quizzes, take them, and see saved scores.
- **Language sessions:** schedule sessions and join them.
- **Roles and reports:** owner tools for roles, reports, bans, and maintenance mode.

SQLite.js is included under `vendor/` and retains its MIT license notice in `vendor/sql.js.LICENSE`.
