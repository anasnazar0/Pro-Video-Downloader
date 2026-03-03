from flask import Flask, render_template

app = Flask(__name__)

# سيرفرك الآن وظيفته الوحيدة هي استضافة صفحة الويب فقط
@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
