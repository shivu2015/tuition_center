from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("home.html")

@app.route("/students")
def students():
    return render_template("students.html")

if __name__ == "__main__":
    app.run(debug=True)