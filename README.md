# Bingo Django

Let's play Bingo, using Django.

Tutorial introducing Python with Django as a REST API server and administrative interface, and a user interface powered with Javascript and React.

# Prompt

I'm creating a tutorial on how to make a bingo game using a Python Django REST API server and administrative interface, and a user interface with Javascript and React. It's going to be simple, to-the-point, and instructive. 

First, we'll bootstrap a Django project. Then will implement the REST API and Admin UI.

The Django API server will power two REST API endpoint, GET /bingo and POST /bingo.

GET /board will return the bingo board for the client specified in the request's cookie and a status parameter showing "started" or "finished". If no client id is specified in the request, then a new board will be generated and the board id will be passed as a cookie in the response. The new board will not have any past numbers from the game marked, but the current number and future numbers will be marked on the board.

POST /bingo will register the specified client as the winner of the bingo game, and the corresponding board state will be checked to verify the win before the game is finished.

We'll use Django REST Framework for these endpoints, and write appropriate unit tests for them as part of the tutorial.

The Django admin UI will use Django's native features here as much as possible, and has to perform two functions: Start or stop a game, and trigger a new number draw in a running game. If a game is started, any board ids from that game are invalidated, and new requests to GET /board with the invalid board ids will get new boards and new board ids in the response. When a new number is drawn for a game, the board state for all boards in that game is updated to mark the number. If a game is stopped, no new numbers may be drawn for that game.

The React front-end will render a bingo board, and begin polling the GET /board endpoint every 100ms, updating the UI whenever it gets a new number. Once a bingo match has been made on the user's board, it will POST /bingo, resume polling, and wait for a new game to start.

The React code will be an index.html file, index.css file, and index.js file, compiled used Vite, and managed using pnpm.

 The tutorial MUST start from the perspective of starting through a bare repo, introduce and explain each step that will be taken, and be organized in an intuitive manner, starting with basics and necessities, before implement core functions that build on each other, and finishing with some polish.

# Django + React Bingo — a minimal, instructive tutorial

> Goal: Build a tiny Bingo game with a Python Django REST API (plus Django Admin) and a React UI. The API exposes two endpoints: `GET /board` and `POST /bingo`. Admin can start/stop a game and draw the next number. The React client polls the board every 100 ms and posts a win when it has bingo.

We’ll start from nothing (a bare repo), add only what we need, implement the core, then finish with a few niceties.

---

## 0) Prerequisites

* Python 3.11+
* Node 18+
* `pnpm` installed (`npm i -g pnpm`)
* Git

---

## 1) Create a bare repo & project layout

```bash
mkdir bingo-tutorial && cd bingo-tutorial
git init

# Two top-level folders: backend (Django) and frontend (React via Vite)
mkdir backend frontend
```

---

## 2) Bootstrap the Django project (backend)

### 2.1 Create a virtualenv & install deps

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install django djangorestframework django-cors-headers
```

### 2.2 Start the Django project & app

```bash
django-admin startproject config .
python manage.py startapp game
```

Your backend tree now:

```
backend/
  config/
    __init__.py
    asgi.py
    settings.py
    urls.py
    wsgi.py
  game/
    __init__.py
    admin.py
    apps.py
    migrations/
    models.py
    tests.py
    views.py
  manage.py
  .venv/
```

### 2.3 Configure settings

Edit `config/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'game',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# Dev: allow frontend origin
CORS_ALLOW_ALL_ORIGINS = True

# DRF basics
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
}

# SQLite for simplicity
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Simple secret key and debug for tutorial
SECRET_KEY = 'dev-only-not-for-prod'
DEBUG = True
ALLOWED_HOSTS = ['*']
```

Add `game/urls.py`:

```python
from django.urls import path
from .views import board_view, bingo_view

urlpatterns = [
    path('board', board_view, name='board'),      # GET /board
    path('bingo', bingo_view, name='bingo'),      # POST /bingo
]
```

Wire into `config/urls.py`:

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('game.urls')),
]
```

---

## 3) Data model & rules

**Key ideas**

* A `Game` tracks status (`started` or `finished`) and the sequence of drawn numbers.
* A `Board` belongs to a `Game`, stores its 5×5 numbers, and remembers the **start draw index**—so boards created mid-game only consider the **current** number (the latest draw at creation time) and future draws (per spec).
* We’ll treat “marking” as: `marks = drawn_numbers[start_draw_index:] ∩ board_numbers`.

Edit `game/models.py`:

```python
import uuid
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import JSONField

class Game(models.Model):
    STATUS_CHOICES = [
        ('started', 'Started'),
        ('finished', 'Finished'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='finished')
    drawn_numbers = JSONField(default=list, blank=True)  # e.g., [5, 42, 18]
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    @property
    def current_number(self):
        return self.drawn_numbers[-1] if self.drawn_numbers else None

    def start(self):
        self.status = 'started'
        self.drawn_numbers = []
        self.started_at = timezone.now()
        self.finished_at = None
        self.save()

    def stop(self):
        self.status = 'finished'
        self.finished_at = timezone.now()
        self.save()

    def draw_number(self):
        import random
        all_nums = list(range(1, 76))
        remaining = [n for n in all_nums if n not in self.drawn_numbers]
        if not remaining:
            return None
        pick = random.choice(remaining)
        self.drawn_numbers.append(pick)
        self.save(update_fields=['drawn_numbers'])
        return pick

    def __str__(self):
        return f"Game {self.id} ({self.status})"

class Board(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='boards')
    numbers = JSONField()  # 5x5 matrix of ints
    start_draw_index = models.PositiveIntegerField(default=0)
    winner = models.BooleanField(default=False)
    won_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def relevant_draws(self):
        return self.game.drawn_numbers[self.start_draw_index:]

    def marks_matrix(self):
        # return 5x5 booleans where True if number in relevant draws
        draws = set(self.relevant_draws())
        return [[cell in draws for cell in row] for row in self.numbers]

    def has_bingo(self):
        m = self.marks_matrix()
        # rows
        for r in range(5):
            if all(m[r]):
                return True
        # cols
        for c in range(5):
            if all(m[r][c] for r in range(5)):
                return True
        # diagonals
        if all(m[i][i] for i in range(5)):
            return True
        if all(m[i][4 - i] for i in range(5)):
            return True
        return False

    def __str__(self):
        return f"Board {self.id} for Game {self.game_id}"
```

Create and run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

---

## 4) Admin: start/stop/draw (native Django admin)

We’ll register `Game` and `Board` and add admin **actions** to start/stop a game and draw a number. Spec: Starting a game invalidates prior boards (because they belong to old games). New boards will be created against the active game.

Edit `game/admin.py`:

```python
from django.contrib import admin
from django.utils.html import format_html
from .models import Game, Board

@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'current_number', 'started_at', 'finished_at', 'created_at')
    actions = ['start_selected', 'stop_selected', 'draw_for_selected']

    @admin.action(description='Start selected game(s)')
    def start_selected(self, request, queryset):
        for g in queryset:
            g.start()

    @admin.action(description='Stop selected game(s)')
    def stop_selected(self, request, queryset):
        for g in queryset:
            g.stop()

    @admin.action(description='Draw next number for selected game(s)')
    def draw_for_selected(self, request, queryset):
        for g in queryset.filter(status='started'):
            g.draw_number()

@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('id', 'game', 'winner', 'created_at', 'won_at', 'start_draw_index')
    readonly_fields = ('id',)
```

Create a superuser to access `/admin/`:

```bash
python manage.py createsuperuser
```

### Using admin during development

* Create a `Game` in admin, select it, **Start** it.
* Use the **Draw next number** action as the caller during gameplay.
* **Stop** when done. While stopped, no new numbers should be drawn.

---

## 5) REST API (DRF): `GET /board` and `POST /bingo`

**Contract**

* `GET /board`:

  * Reads `board_id` cookie.
  * If missing or invalid or not for the active game, and there is an active game → create a **new Board**:

    * Its `start_draw_index` is set to the current length of the game’s draw list minus 1 (so **only the current latest number** counts, not earlier ones). If no numbers drawn yet, `start_draw_index = len(draws)`.
  * Returns JSON: `{ status: 'started'|'finished', board_id, numbers: 5x5, marks: 5x5, current_number }`.
  * If no active game, returns `{ status: 'finished' }`.
* `POST /bingo`:

  * Reads `board_id` cookie (or JSON body fallback), loads that Board.
  * Validates server-side `has_bingo()` against **relevant draws**.
  * If valid, marks board as winner, and responds `{ ok: true }`. If invalid, `{ ok: false }`.

Create `game/serializers.py`:

```python
from rest_framework import serializers
from .models import Board

class BoardSerializer(serializers.ModelSerializer):
    marks = serializers.SerializerMethodField()
    current_number = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Board
        fields = ['id', 'numbers', 'marks', 'current_number', 'status']

    def get_marks(self, obj):
        return obj.marks_matrix()

    def get_current_number(self, obj):
        return obj.game.current_number

    def get_status(self, obj):
        return obj.game.status
```

Edit `game/views.py`:

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Game, Board
from .serializers import BoardSerializer
import random

COOKIE_NAME = 'board_id'

@api_view(['GET'])
@permission_classes([AllowAny])
def board_view(request):
    # Get the latest active game (if any)
    active = Game.objects.filter(status='started').order_by('-started_at').first()
    if not active:
        return Response({'status': 'finished'})

    board_id = request.COOKIES.get(COOKIE_NAME)
    board = None

    if board_id:
        try:
            b = Board.objects.get(id=board_id)
            if b.game_id == active.id:
                board = b
        except Board.DoesNotExist:
            pass

    # Create a new board if missing/invalid
    if board is None:
        nums = generate_board_numbers()
        # per spec: only current number and future numbers count
        start_idx = max(0, len(active.drawn_numbers) - 1) if active.drawn_numbers else 0
        board = Board.objects.create(game=active, numbers=nums, start_draw_index=start_idx)

    ser = BoardSerializer(board)
    resp = Response({
        'status': ser.data['status'],
        'board_id': str(board.id),
        'numbers': ser.data['numbers'],
        'marks': ser.data['marks'],
        'current_number': ser.data['current_number'],
    })
    resp.set_cookie(COOKIE_NAME, str(board.id), samesite='Lax')
    return resp

@api_view(['POST'])
@permission_classes([AllowAny])
def bingo_view(request):
    board_id = request.COOKIES.get(COOKIE_NAME) or request.data.get('board_id')
    if not board_id:
        return Response({'ok': False, 'error': 'missing board'}, status=400)

    board = get_object_or_404(Board, id=board_id)
    game = board.game
    if game.status != 'started':
        return Response({'ok': False, 'error': 'game not started'}, status=400)

    if board.has_bingo():
        board.winner = True
        board.won_at = timezone.now()
        board.save(update_fields=['winner', 'won_at'])
        return Response({'ok': True})

    return Response({'ok': False})

# Helpers

def generate_board_numbers():
    # Standard 75-ball bingo: 5 columns of ranges, 5 rows, center can be free if you want.
    # Here we keep it simple: pick 25 unique numbers from 1..75 and lay them out row-wise.
    pool = list(range(1, 76))
    random.shuffle(pool)
    pick = pool[:25]
    return [pick[i*5:(i+1)*5] for i in range(5)]
```

Add `__init__.py` imports (optional) or leave as-is.

Run server:

```bash
python manage.py runserver 8000
```

* `GET http://localhost:8000/board` → returns a JSON board (and sets `board_id` cookie).
* `POST http://localhost:8000/bingo` → sends win claim.

---

## 6) Unit tests

We’ll use Django’s built-in TestCase.

Edit `game/tests.py`:

```python
from django.test import TestCase, Client
from django.urls import reverse
from .models import Game, Board

class BoardApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.game = Game.objects.create(status='finished')

    def test_get_board_no_active_game(self):
        resp = self.client.get(reverse('board'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'finished')

    def test_get_board_active_game_creates_board_and_cookie(self):
        self.game.start()
        resp = self.client.get(reverse('board'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'started')
        self.assertIn('board_id', data)
        self.assertIn('board_id', resp.cookies)

    def test_board_respects_start_draw_index_current_only(self):
        self.game.start()
        # draw three numbers; creating a board now should only count the current/latest number
        self.game.draw_number()
        self.game.draw_number()
        self.game.draw_number()
        resp = self.client.get(reverse('board'))
        data = resp.json()
        # count marks; should be <=1 per row unless coincidence; conservatively check that earlier draws are not counted
        marks = data['marks']
        # flatten
        marked_count = sum(1 for r in marks for x in r if x)
        # since only the latest draw may or may not be on the board, marked_count should be 0 or a few but not 3
        self.assertLess(marked_count, 3)

    def test_cookie_board_reused_same_active_game(self):
        self.game.start()
        resp = self.client.get(reverse('board'))
        bid = resp.json()['board_id']
        self.client.cookies['board_id'] = bid
        resp2 = self.client.get(reverse('board'))
        self.assertEqual(bid, resp2.json()['board_id'])

    def test_old_board_invalidated_on_new_game(self):
        self.game.start()
        r1 = self.client.get(reverse('board'))
        old_bid = r1.json()['board_id']
        # stop old game and start new one
        self.game.stop()
        g2 = Game.objects.create(status='finished')
        g2.start()
        self.client.cookies['board_id'] = old_bid
        r2 = self.client.get(reverse('board'))
        self.assertNotEqual(old_bid, r2.json()['board_id'])

class BingoPostTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.game = Game.objects.create(status='finished')
        self.game.start()

    def _make_board_with_numbers(self, rows):
        return Board.objects.create(game=self.game, numbers=rows, start_draw_index=0)

    def test_reject_when_no_bingo(self):
        b = self._make_board_with_numbers([
            [1,2,3,4,5],
            [6,7,8,9,10],
            [11,12,13,14,15],
            [16,17,18,19,20],
            [21,22,23,24,25],
        ])
        # draw numbers that don't complete a line
        self.game.drawn_numbers = [1,7,13,19]  # missing 25 for diagonal, for example
        self.game.save()
        self.client.cookies['board_id'] = str(b.id)
        r = self.client.post(reverse('bingo'))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['ok'])

    def test_accept_when_bingo(self):
        b = self._make_board_with_numbers([
            [1,2,3,4,5],
            [6,7,8,9,10],
            [11,12,13,14,15],
            [16,17,18,19,20],
            [21,22,23,24,25],
        ])
        # complete first row
        self.game.drawn_numbers = [1,2,3,4,5]
        self.game.save()
        self.client.cookies['board_id'] = str(b.id)
        r = self.client.post(reverse('bingo'))
        self.assertTrue(r.json()['ok'])
        b.refresh_from_db()
        self.assertTrue(b.winner)
        self.assertIsNotNone(b.won_at)
```

Run tests:

```bash
python manage.py test
```

---

## 7) Frontend (React + Vite + pnpm)

### 7.1 Bootstrap Vite app

```bash
cd ../frontend
pnpm create vite@latest . --template vanilla  # we’ll wire React manually for minimal files
pnpm add react react-dom
pnpm add -D @types/react @types/react-dom vite
```

Replace `index.html` with this minimal document:

```html
<!doctype html>
<html>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Bingo</title>
    <link rel="stylesheet" href="/index.css" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/index.js"></script>
  </body>
</html>
```

Create `index.css`:

```css
:root { font-family: system-ui, sans-serif; }
body { margin: 0; display: grid; place-items: center; min-height: 100vh; background: #111; color: #eee; }
.board { display: grid; grid-template-columns: repeat(5, 64px); gap: 8px; }
.cell { width: 64px; height: 64px; display: grid; place-items: center; border: 1px solid #444; border-radius: 8px; background: #222; font-weight: 700; }
.cell.marked { background: #3a6; }
.hud { margin-top: 16px; font-size: 14px; opacity: 0.8; }
.btns { margin-top: 12px; display: flex; gap: 8px; }
button { padding: 8px 12px; border: 0; border-radius: 8px; cursor: pointer; }
```

Create `index.js`:

```js
import React, { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'

const API = 'http://localhost:8000'

function usePollBoard(intervalMs = 100) {
  const [data, setData] = useState({ status: 'finished' })
  const timer = useRef(null)

  useEffect(() => {
    let stopped = false
    async function tick() {
      try {
        const res = await fetch(`${API}/board`, { credentials: 'include' })
        const json = await res.json()
        if (!stopped) setData(json)
      } catch (e) { /* ignore in demo */ }
      if (!stopped) timer.current = setTimeout(tick, intervalMs)
    }
    tick()
    return () => { stopped = true; if (timer.current) clearTimeout(timer.current) }
  }, [intervalMs])

  return data
}

function hasLocalBingo(marks) {
  if (!marks) return false
  // rows
  for (let r = 0; r < 5; r++) if (marks[r].every(Boolean)) return true
  // cols
  for (let c = 0; c < 5; c++) {
    let ok = true
    for (let r = 0; r < 5; r++) if (!marks[r][c]) { ok = false; break }
    if (ok) return true
  }
  // diags
  if ([0,1,2,3,4].every(i => marks[i][i])) return true
  if ([0,1,2,3,4].every(i => marks[i][4-i])) return true
  return false
}

function App() {
  const data = usePollBoard(100)
  const [claimed, setClaimed] = useState(false)

  useEffect(() => {
    // Auto-POST /bingo once when we see bingo
    async function claim() {
      try {
        const res = await fetch(`${API}/bingo`, { method: 'POST', credentials: 'include' })
        const json = await res.json()
        setClaimed(json.ok)
      } catch {}
    }
    if (data.status === 'started' && hasLocalBingo(data.marks) && !claimed) {
      claim()
    }
    if (data.status === 'finished') setClaimed(false)
  }, [data, claimed])

  const { numbers, marks, current_number, status } = data

  return (
    <div>
      <h1 style={{textAlign:'center'}}>Bingo</h1>
      {status === 'finished' && <p className="hud">Waiting for a new game…</p>}
      {numbers && (
        <div className="board">
          {numbers.flat().map((n, i) => (
            <div key={i} className={"cell" + (marks?.flat?.()[i] ? ' marked' : '')}>{n}</div>
          ))}
        </div>
      )}
      <div className="hud">
        <div>Status: <b>{status}</b>{current_number ? ` — current: ${current_number}` : ''}</div>
        <div>{claimed ? 'Bingo claimed! Waiting for next game…' : ''}</div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')).render(<App />)
```

Run the frontend:

```bash
pnpm dev
```

Visit `http://localhost:5173` (default Vite dev port). The browser will send cookies and poll your Django API.

> Tip: If you don’t see data, ensure Django runs on `http://localhost:8000` and that a `Game` is **Started** in `/admin/`.

---

## 8) Cross-origin & cookies

We set `CORS_ALLOW_ALL_ORIGINS = True` for simplicity. In real projects, whitelist your frontend origin and consider CSRF + HTTPS. We also use `credentials: 'include'` so the `board_id` cookie persists.

---

## 9) How the “current-only then future” rule works

When a board is created mid-game, we set:

```python
start_idx = max(0, len(active.drawn_numbers) - 1) if active.drawn_numbers else 0
```

So only the **latest draw at creation** and all **future draws** count toward marks. Earlier draws don’t count for that board. Boards created before any draw simply use `0`.

---

## 10) Quick workflow to demo

1. **Backend**: `cd backend && source .venv/bin/activate && python manage.py runserver 8000`.
2. **Admin**: `http://localhost:8000/admin/` → create Game → **Start** it.
3. **Frontend**: `cd ../frontend && pnpm dev` → open the app.
4. In Admin, use **Draw next number** a few times. Watch cells turn green.
5. Once a row/col/diag completes, the frontend calls `POST /bingo`. You’ll see “Bingo claimed!”.
6. **Stop** the game in admin. Frontend shows “Waiting for a new game…”. Start another game to reset everyone.

---

## 11) Optional polish

* **Center “free” space**: set `numbers[2][2] = 0` and treat `0` as always marked.
* **Persist winners**: add admin filters for winners and display a leaderboard.
* **Deterministic draws**: replace random with a queue to make demos reproducible.
* **Rate-limit** polling: 100 ms is per spec; in practice, consider Server-Sent Events or WebSockets.
* **Validation**: record winner order (first wins), and automatically `stop()` when a winner is verified.

---

## 12) FAQ

**Why `GET /board` and not `GET /bingo`?** The spec describes two endpoints, then details `GET /board` + `POST /bingo`. This tutorial implements those two.

**Do we “update all boards” on draw?** We update the `Game.drawn_numbers`; each board derives its marks from that list (post its `start_draw_index`). That keeps writes minimal and logic clean while meeting the behavior described.

**Can I seed the RNG?** Yes—set `random.seed()` in `draw_number()` or inject your own picker.

---

You now have a compact, didactic Bingo game: Django REST + Admin on the back, React on the front, with tests and clear rules. Have fun extending it!