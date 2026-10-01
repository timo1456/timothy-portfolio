import json, os, secrets
from pathlib import Path
from flask import Flask, abort, redirect, render_template, request, session, url_for, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix
BASE_DIR=Path(__file__).resolve().parent
STORAGE_DIR=Path(os.environ.get("PORTFOLIO_STORAGE_PATH", str(BASE_DIR/"data")))
DATA_DIR=STORAGE_DIR; UPLOAD_DIR=STORAGE_DIR/"uploads"
PROJECTS_FILE=DATA_DIR/"projects.json"; CERTS_FILE=DATA_DIR/"certifications.json"; VISITS_FILE=DATA_DIR/"site_visits.json"
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","dev-change-this-secret-key")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("RENDER")=="true")
ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD","change-me")
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1)
DATA_DIR.mkdir(exist_ok=True); UPLOAD_DIR.mkdir(exist_ok=True)
def load_json(path, default):
    if not path.exists(): path.write_text(json.dumps(default,indent=2),encoding="utf-8")
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError,OSError): return default
def save_json(path,data): path.write_text(json.dumps(data,indent=2),encoding="utf-8")
def get_projects(): return load_json(PROJECTS_FILE,[])
def get_certs(): return load_json(CERTS_FILE,[])
def get_visits():
    return load_json(VISITS_FILE,[])

def log_visit():
    visits=get_visits()
    visits.append({
        "ip": request.remote_addr or "Unknown",
        "checked_in": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(timespec="seconds")
    })
    save_json(VISITS_FILE,visits[-500:])
def admin_required():
    if not session.get("admin"): return redirect(url_for("admin_login"))
@app.context_processor
def globals():
    return {"site_name":"Idowu Timothy","email":"timothypraiseofficial@gmail.com","github":"https://github.com/timo1456"}
@app.get("/")
def home():
    log_visit()
    return render_template("index.html",projects=[p for p in get_projects() if p.get("featured")][:6],certifications=get_certs())
@app.get("/projects")
def projects(): return render_template("projects.html",projects=get_projects())
@app.get("/projects/<int:project_id>")
def project(project_id):
    item=next((p for p in get_projects() if p.get("id")==project_id),None)
    if not item: abort(404)
    return render_template("project.html",project=item)
@app.get("/admin")
def admin():
    auth=admin_required()
    return auth or render_template("admin/dashboard.html",projects=get_projects(),certifications=get_certs(),visits=list(reversed(get_visits())))
@app.route("/admin/login",methods=["GET","POST"])
def admin_login():
    error=None
    if request.method=="POST":
        if secrets.compare_digest(request.form.get("password",""),ADMIN_PASSWORD):
            session["admin"]=True; return redirect(url_for("admin"))
        error="Incorrect password."
    return render_template("admin/login.html",error=error)
@app.post("/admin/logout")
def admin_logout(): session.clear(); return redirect(url_for("admin_login"))
@app.route("/admin/projects/new",methods=["GET","POST"])
def new_project():
    auth=admin_required()
    if auth: return auth
    if request.method=="POST":
        projects=get_projects(); next_id=max([p.get("id",0) for p in projects] or [0])+1
        image=request.files.get("image"); image_name=""
        if image and image.filename:
            name=secrets.token_hex(6)+"-"+Path(image.filename).name.replace(" ","-"); image.save(UPLOAD_DIR/name); image_name="/uploads/"+name
        projects.append({"id":next_id,"name":request.form.get("name","").strip(),"description":request.form.get("description","").strip(),"image_url":image_name,"project_url":request.form.get("project_url","").strip(),"featured":request.form.get("featured")=="on"})
        save_json(PROJECTS_FILE,projects); return redirect(url_for("admin"))
    return render_template("admin/project_form.html",editing=False,project=None)

@app.route("/admin/projects/<int:project_id>/edit",methods=["GET","POST"])
def edit_project(project_id):
    auth=admin_required()
    if auth: return auth
    projects=get_projects()
    item=next((p for p in projects if p.get("id")==project_id),None)
    if not item: abort(404)
    if request.method=="POST":
        item["name"]=request.form.get("name","").strip()
        item["description"]=request.form.get("description","").strip()
        item["project_url"]=request.form.get("project_url","").strip()
        item["featured"]=request.form.get("featured")=="on"
        image=request.files.get("image")
        if image and image.filename:
            name=secrets.token_hex(6)+"-"+Path(image.filename).name.replace(" ","-")
            image.save(UPLOAD_DIR/name)
            item["image_url"]="/uploads/"+name
        save_json(PROJECTS_FILE,projects)
        return redirect(url_for("admin"))
    return render_template("admin/project_form.html",editing=True,project=item)
@app.post("/admin/projects/<int:project_id>/delete")
def delete_project(project_id):
    auth=admin_required()
    if auth: return auth
    save_json(PROJECTS_FILE,[p for p in get_projects() if p.get("id")!=project_id]); return redirect(url_for("admin"))
@app.route("/admin/certifications/new",methods=["GET","POST"])
def new_certification():
    auth=admin_required()
    if auth: return auth
    if request.method=="POST":
        certs=get_certs(); next_id=max([c.get("id",0) for c in certs] or [0])+1
        file=request.files.get("file"); file_url=""; file_type=""
        if file and file.filename:
            ext=Path(file.filename).suffix.lower()
            if ext not in {".jpg",".jpeg",".png",".webp",".pdf"}: return render_template("admin/cert_form.html",error="Use an image or PDF.",editing=False,cert=None)
            name=secrets.token_hex(6)+"-"+Path(file.filename).name.replace(" ","-"); file.save(UPLOAD_DIR/name); file_url="/uploads/"+name; file_type=ext.lstrip(".")
        certs.append({"id":next_id,"name":request.form.get("name","").strip(),"issuer":request.form.get("issuer","").strip(),"date":request.form.get("date","").strip(),"file_url":file_url,"file_type":file_type})
        save_json(CERTS_FILE,certs); return redirect(url_for("admin"))
    return render_template("admin/cert_form.html",error=None,editing=False,cert=None)

@app.route("/admin/certifications/<int:cert_id>/edit",methods=["GET","POST"])
def edit_certification(cert_id):
    auth=admin_required()
    if auth: return auth
    certs=get_certs()
    item=next((c for c in certs if c.get("id")==cert_id),None)
    if not item: abort(404)
    if request.method=="POST":
        item["name"]=request.form.get("name","").strip()
        item["issuer"]=request.form.get("issuer","").strip()
        item["date"]=request.form.get("date","").strip()
        file=request.files.get("file")
        if file and file.filename:
            ext=Path(file.filename).suffix.lower()
            if ext not in {".jpg",".jpeg",".png",".webp",".pdf"}:
                return render_template("admin/cert_form.html",error="Use an image or PDF.",editing=True,cert=item)
            name=secrets.token_hex(6)+"-"+Path(file.filename).name.replace(" ","-")
            file.save(UPLOAD_DIR/name)
            item["file_url"]="/uploads/"+name
            item["file_type"]=ext.lstrip(".")
        save_json(CERTS_FILE,certs)
        return redirect(url_for("admin"))
    return render_template("admin/cert_form.html",error=None,editing=True,cert=item)
@app.post("/admin/certifications/<int:cert_id>/delete")
def delete_certification(cert_id):
    auth=admin_required()
    if auth: return auth
    save_json(CERTS_FILE,[c for c in get_certs() if c.get("id")!=cert_id]); return redirect(url_for("admin"))
@app.get("/IMG_20260125_132037_097~2.jpg")
def profile_photo(): return send_from_directory(BASE_DIR, "IMG_20260125_132037_097~2.jpg")
@app.get("/certifications/<int:cert_id>")
def certification(cert_id):
    item=next((c for c in get_certs() if c.get("id")==cert_id),None)
    if not item: abort(404)
    if not item.get("file_type") and item.get("file_url"):
        item["file_type"]=Path(item["file_url"]).suffix.lower().lstrip(".")
    return render_template("certification.html", cert=item)
@app.get("/uploads/<path:filename>")
def uploads(filename): return send_from_directory(UPLOAD_DIR,filename)
@app.get("/health")
def health(): return {"status":"ok"}
if __name__=="__main__": app.run(debug=True)
