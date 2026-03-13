import os
import secrets
from typing import Optional
from fastapi import FastAPI, Depends, Request, Form, HTTPException, Cookie, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from itsdangerous import URLSafeSerializer

from models import Base, engine, get_db, Category, Subcategory, Idea, init_db

app = FastAPI(title="Brainstorming Ideas PWA")

# Initialize DB on startup
@app.on_event("startup")
def startup():
    init_db()

# Security & Sessions
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
serializer = URLSafeSerializer(SECRET_KEY)
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123") # Default for development
SESSION_COOKIE_NAME = "session_id"

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Auth Helper
def get_current_user(session_id: Optional[str] = Cookie(None)):
    if not session_id:
        return None
    try:
        data = serializer.loads(session_id)
        if data == "admin":
            return "admin"
    except:
        return None
    return None

def login_required(request: Request, user=Depends(get_current_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user

# Routes
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        session_id = serializer.dumps("admin")
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key=SESSION_COOKIE_NAME, value=session_id, httponly=True)
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Credenciales inválidas"})

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    categories = db.query(Category).all()
    # If no category exists, we might want to suggest creating one
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "categories": categories,
        "user": user
    })

# HTMX CRUD for Categories
@app.post("/categories")
async def create_category(name: str = Form(...), db: Session = Depends(get_db), user=Depends(login_required)):
    new_cat = Category(name=name)
    db.add(new_cat)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/categories/{cat_id}/edit")
async def edit_category(cat_id: int, name: str = Form(...), db: Session = Depends(get_db), user=Depends(login_required)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if cat:
        cat.name = name
        db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/categories/{cat_id}/delete")
async def delete_category(cat_id: int, db: Session = Depends(get_db), user=Depends(login_required)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if cat:
        db.delete(cat)
        db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# HTMX CRUD for Subcategories
@app.post("/subcategories")
async def create_subcategory(name: str = Form(...), category_id: int = Form(...), db: Session = Depends(get_db), user=Depends(login_required)):
    new_sub = Subcategory(name=name, category_id=category_id)
    db.add(new_sub)
    db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/subcategories/{sub_id}/edit")
async def edit_subcategory(sub_id: int, name: str = Form(...), db: Session = Depends(get_db), user=Depends(login_required)):
    sub = db.query(Subcategory).filter(Subcategory.id == sub_id).first()
    if sub:
        sub.name = name
        db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/subcategories/{sub_id}/delete")
async def delete_subcategory(sub_id: int, db: Session = Depends(get_db), user=Depends(login_required)):
    sub = db.query(Subcategory).filter(Subcategory.id == sub_id).first()
    if sub:
        db.delete(sub)
        db.commit()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# HTMX CRUD for Ideas
@app.get("/api/ideas")
async def list_ideas(request: Request, subcategory_id: Optional[int] = None, db: Session = Depends(get_db), user=Depends(login_required)):
    query = db.query(Idea)
    if subcategory_id:
        query = query.filter(Idea.subcategory_id == subcategory_id)
    ideas = query.order_by(Idea.created_at.desc()).all()
    # For HTMX, return a partial if needed, or just JSON if frontend handles it. 
    # Let's return a partial HTML for the grid.
    return templates.TemplateResponse("partials/idea_grid.html", {"request": request, "ideas": ideas})

@app.post("/ideas")
async def create_idea(
    title: str = Form(...), 
    description: str = Form(...), 
    url: Optional[str] = Form(None), 
    status: str = Form("Idea"), 
    subcategory_id: int = Form(...), 
    db: Session = Depends(get_db), 
    user=Depends(login_required)
):
    new_idea = Idea(
        title=title, 
        description=description, 
        url=url, 
        status=status, 
        subcategory_id=subcategory_id
    )
    db.add(new_idea)
    db.commit()
    # Trigger HTMX refresh of the grid for that subcategory
    return Response(headers={"HX-Trigger": "ideaChanged"})

@app.post("/ideas/{idea_id}/edit")
async def edit_idea(
    idea_id: int,
    title: str = Form(...), 
    description: str = Form(...), 
    url: Optional[str] = Form(None), 
    status: str = Form("Idea"), 
    db: Session = Depends(get_db), 
    user=Depends(login_required)
):
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if idea:
        idea.title = title
        idea.description = description
        idea.url = url
        idea.status = status
        db.commit()
    return Response(headers={"HX-Trigger": "ideaChanged"})

@app.post("/ideas/{idea_id}/delete")
async def delete_idea(idea_id: int, db: Session = Depends(get_db), user=Depends(login_required)):
    idea = db.query(Idea).filter(Idea.id == idea_id).first()
    if idea:
        db.delete(idea)
        db.commit()
    return Response(headers={"HX-Trigger": "ideaChanged"})

@app.get("/manifest.json")
async def manifest():
    return FileResponse("static/manifest.json")
