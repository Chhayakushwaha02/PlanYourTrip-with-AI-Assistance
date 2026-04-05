from flask import Flask, render_template, request, jsonify, redirect, session, url_for
import mysql.connector
from datetime import datetime
from authlib.integrations.flask_client import OAuth
import google.generativeai as genai
from dotenv import load_dotenv
import os

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# ---------------- DATABASE CONNECTION ----------------
db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)
cursor = db.cursor(dictionary=True)

# ---------------- OAUTH CONFIGURATION ----------------
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    access_token_url='https://oauth2.googleapis.com/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    userinfo_endpoint='https://www.googleapis.com/oauth2/v3/userinfo',
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'consent',
        'access_type': 'offline'
    },
)



# ---------------- splash PAGE ----------------
@app.route("/splash")
def splash():
    return render_template("splash.html")

# ---------------- AUTH PAGE ----------------
@app.route("/")
def splash_page():
    return render_template("splash.html")


@app.route("/auth")
def auth_page():
    return render_template("auth.html")

# ---------------- GOOGLE LOGIN ----------------
# Google OAuth login
@app.route("/login/google")
def login_google():
    # Make sure redirect URI matches EXACTLY with Google Cloud Console
    redirect_uri = url_for('authorize_google', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/authorize")
def authorize_google():
    try:
        token = google.authorize_access_token()
        user_info = google.parse_id_token(token)

        email = user_info['email']
        name = user_info.get('name', 'User')

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if not user:
            cursor.execute(
                "INSERT INTO users(username,email,created_at) VALUES(%s,%s,%s)",
                (name, email, datetime.now())
            )
            db.commit()
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cursor.fetchone()

        session["user_id"] = user["id"]
        session["username"] = user["username"]

        return redirect("/dashboard")

    except Exception as e:
        print("GOOGLE LOGIN ERROR:", e)
        return "Google login failed. Check console for details."
    

# ---------------- EMAIL/PASSWORD LOGIN ----------------
@app.route("/login", methods=["POST"])
def login_email():
    data = request.get_json()
    email = data["email"]
    password = data["password"]

    cursor.execute(
        "SELECT * FROM users WHERE email=%s AND password=%s",
        (email, password)
    )
    user = cursor.fetchone()

    if user:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        return jsonify({"success": True, "redirect_url": "/dashboard"})
    else:
        return jsonify({"success": False, "message": "Invalid email or password"})

# ---------------- REGISTER ----------------
@app.route("/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data["name"]
    email = data["email"]
    age = data.get("age")
    gender = data.get("gender")
    mobile = data.get("mobile")
    password = data["password"]

    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    if cursor.fetchone():
        return jsonify({"success": False, "message": "Email already registered"})

    cursor.execute(
        "INSERT INTO users(username,email,age,gender,mobile,password,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (username, email, age, gender, mobile, password, datetime.now())
    )
    db.commit()
    return jsonify({"success": True, "message": "Registration successful"})

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")
    return render_template("dashboard.html", username=session["username"])

# ---------------- PLAN TRIP ----------------
@app.route("/plantrip")
def plantrip():
    if "user_id" not in session:
        return redirect("/")
    return render_template("plantrip.html", username=session["username"])


# ---------------- SAVE TRIP ----------------
@app.route("/save_trip", methods=["POST"])
def save_trip():

    if "user_id" not in session:
        return "Unauthorized"

    destination = request.form["destination"]
    starting_location = request.form["starting_location"]
    start_date = request.form["start_date"]
    end_date = request.form["end_date"]
    budget = request.form["budget"]
    days = request.form["days"]
    trip_type = request.form["trip_type"]

    cursor.execute("""
        INSERT INTO trips
        (user_id, destination, starting_location, start_date, end_date, budget, days, trip_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        session["user_id"],
        destination,
        starting_location,
        start_date,
        end_date,
        budget,
        days,
        trip_type
    ))

    db.commit()

    return "Success"


@app.route("/generate_trip", methods=["POST"])
def generate_trip():

    if "user_id" not in session:
        return redirect("/")

    # ✅ Get latest trip
    cursor.execute("""
        SELECT * FROM trips
        WHERE user_id=%s
        ORDER BY id DESC LIMIT 1
    """, (session["user_id"],))

    trip = cursor.fetchone()

    if not trip:
        return "❌ Please save trip details first!"

    # ✅ Create prompt
    prompt = f"""
Trip Planning Request:

Starting Location: {trip[2]}
Destination: {trip[1]}
Trip Duration: {trip[6]} days
Budget: ₹{trip[5]}
Trip Type: {trip[7]}

Provide:
1. Best transport option
2. Weather awareness
3. Budget breakdown
4. Day wise itinerary
5. Travel tips
"""

    # ✅ Send to chatbot page
    return render_template("chatbot.html", prompt=prompt)


# ---------------- CHATBOT ----------------
@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")

# ---------------- MY TRIPS ----------------
@app.route("/mytrips")
def mytrips():

    if "user_id" not in session:
        return redirect("/")

    cursor.execute(
        "SELECT * FROM trips WHERE user_id=%s",
        (session["user_id"],)
    )

    trips = cursor.fetchall()

    return render_template("mytrips.html", trips=trips)


@app.route('/calculator')
def calculator():
    return render_template('calculator.html')

@app.route("/delete_trip/<int:trip_id>", methods=["POST"])
def delete_trip(trip_id):
    try:
        cursor.execute(
            "DELETE FROM trips WHERE id=%s AND user_id=%s",
            (trip_id, session["user_id"])
        )
        db.commit()   # ✅ IMPORTANT

        return {"success": True}

    except Exception as e:
        print("DELETE ERROR:", e)
        return {"success": False}

# ---------------- EXPLORE DESTINATIONS ----------------
@app.route("/explore")
def explore():
    if "user_id" not in session:
        return redirect("/")
    return render_template("exploredestinations.html", username=session["username"])

# ---------------- PROFILE ----------------
@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect("/")
    cursor.execute("SELECT * FROM users WHERE id=%s", (session["user_id"],))
    user = cursor.fetchone()
    return render_template("profile.html", username=session["username"], user=user)

@app.route("/edit_profile", methods=["GET","POST"])
def edit_profile():
    if "user_id" not in session:
        return redirect("/")

    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        age = request.form.get("age")
        gender = request.form.get("gender")
        mobile = request.form.get("mobile")

        cursor.execute("""
            UPDATE users
            SET username=%s, email=%s, age=%s, gender=%s, mobile=%s
            WHERE id=%s
        """,(username,email,age,gender,mobile,session["user_id"]))
        db.commit()
        return redirect("/profile")

    cursor.execute("SELECT * FROM users WHERE id=%s",(session["user_id"],))
    user = cursor.fetchone()
    return render_template("edit_profile.html", user=user)

# ---------------- CHANGE PASSWORD ----------------
@app.route("/change_password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect("/")

    if request.method == "POST":
        old_password = request.form["old_password"]
        new_password = request.form["new_password"]

        cursor.execute("SELECT password FROM users WHERE id=%s", (session["user_id"],))
        user = cursor.fetchone()

        if user["password"] == old_password:
            cursor.execute("UPDATE users SET password=%s WHERE id=%s", (new_password, session["user_id"]))
            db.commit()
            return redirect("/profile")
        else:
            return "Current password is incorrect"

    return render_template("change_password.html")

# ---------------- EXISTING FORGOT/RESET PASSWORD (DO NOT TOUCH) ----------------
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"]
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if user:
            session["reset_user_id"] = user["id"]
            return redirect("/reset_password")
        else:
            return "Email not found. Please try again."
    return render_template("forgot_password.html")

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if "reset_user_id" not in session:
        return redirect("/forgot_password")

    if request.method == "POST":
        new_password = request.form["new_password"]
        cursor.execute("UPDATE users SET password=%s WHERE id=%s", (new_password, session["reset_user_id"]))
        db.commit()
        session.pop("reset_user_id", None)
        return "Password has been reset successfully! <a href='/'>Login here</a>"

    return render_template("reset_password.html")

# ---------------- AJAX FORGOT/RESET PASSWORD INSIDE LOGIN PAGE ----------------
@app.route("/forgot_password_ajax", methods=["POST"])
def forgot_password_ajax():
    data = request.get_json()
    email = data.get("email")
    cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()
    if user:
        session["reset_user_id"] = user["id"]
        return jsonify({"success": True, "message": "Email verified. You can reset your password now."})
    else:
        return jsonify({"success": False, "message": "Email not found."})

@app.route("/reset_password_ajax", methods=["POST"])
def reset_password_ajax():
    if "reset_user_id" not in session:
        return jsonify({"success": False, "message": "Session expired. Please verify email again."})

    data = request.get_json()
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not new_password or not confirm_password:
        return jsonify({"success": False, "message": "Please enter all fields."})
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "Passwords do not match."})

    cursor.execute(
        "UPDATE users SET password=%s WHERE id=%s",
        (new_password, session["reset_user_id"])
    )
    db.commit()
    session.pop("reset_user_id", None)
    return jsonify({"success": True, "message": "Password reset successfully."})

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------------- RUN SERVER ----------------
if __name__ == "__main__":
    app.run(debug=True)