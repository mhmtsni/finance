import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""
    id = session["user_id"]
    if request.method == "GET":
        stock_info = db.execute("SELECT * FROM stocks WHERE user_id = ?", id)
        cash = db.execute("SELECT cash FROM users WHERE id = ?", id)
        grand_total = 0
        for stock in stock_info:
            stock["current_price"] = lookup(stock["symbol"])["price"]
            stock["total_value"] = stock["amount"] * stock["current_price"]
            grand_total += stock["total_value"]
        grand_total += cash[0]["cash"]
        return render_template("index.html", stocks=stock_info, cash=cash[0]["cash"], total=grand_total)
    else:
        amount = float(request.form.get("cash"))
        if not isinstance(amount, (float, int)):
            return apology("Please enter a number")
        if amount <= 0:
            return apology("The amount cannot be negative")
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", amount, id)
        return redirect("/")

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        symbol = request.form.get("symbol")
        amount = request.form.get("shares")
        stock_info = lookup(symbol)
        id = session["user_id"]
        cash = db.execute("SELECT cash FROM users WHERE id = ?", id)
        stocks_owned = db.execute("SELECT symbol FROM stocks WHERE user_id = ?", id)
        owned_symbols = [stock['symbol'] for stock in stocks_owned]
        
        if not isinstance(amount, int):
            return apology("Please enter a number", 400)
        if amount <= 0:
            return apology("The amount cannot be negative", 400)
        if not stock_info:
            return apology(f"No stock named {symbol}", 400)
        if stock_info["price"] * amount > cash[0]["cash"]:
            return apology("You do not have enough money")
        else:
            remaining_cash = cash[0]["cash"] - (stock_info["price"] * amount)
            if symbol in owned_symbols:
                db.execute("UPDATE stocks SET amount = amount + ?, bought_at = (bought_at + ?) / 2 WHERE symbol = ? AND user_id = ?", amount, stock_info["price"], symbol, id)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", remaining_cash, id)
                db.execute("INSERT INTO history (user_id, symbol, action, amount, price) VALUES(?, ?, ?, ?, ?)", id, symbol, "buy", amount, stock_info["price"])
                return redirect("/")
            else:
                db.execute("INSERT INTO stocks (user_id, stock_name, amount, bought_at, symbol) VALUES(?, ?, ?, ?, ?)", id, stock_info["name"], amount, stock_info["price"], symbol)
                db.execute("UPDATE users SET cash = ? WHERE id = ?", remaining_cash, id)
                db.execute("INSERT INTO history (user_id, symbol, action, amount, price) VALUES(?, ?, ?, ?, ?)", id, symbol, "buy", amount, stock_info["price"])
                return redirect("/")
            
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    id = session["user_id"]
    stock_info = db.execute("SELECT * FROM history WHERE user_id = ?", id)
    return render_template("history.html", stocks=stock_info)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        stock_info = lookup(symbol)
        if not symbol:
            return apology(f"Don't leave it empty", 400)

        if not stock_info:
            return apology(f"No stock named {symbol}", 400)
        else:
            return render_template("quoted.html", name=stock_info["name"], price=stock_info["price"], symbol=stock_info["symbol"])
    else: 
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        all_usernames = db.execute("SELECT username FROM users")
        user_name = request.form.get("username")
        password = request.form.get("password")
        confirmation_password = request.form.get("confirmation")
        hashed_password = generate_password_hash(password)
        if password != confirmation_password:
            return apology("Passwords do not match", 400)
        if not password or not user_name:
            return apology("Please provide a user name and a password", 400)
        for row in all_usernames:  
            
            if user_name == row["username"]:
                return apology("User name taken", 400)
        else: 
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", user_name, hashed_password)
            id = db.execute("SELECT id FROM users WHERE username = ?", user_name)
            session["user_id"] = id[0]["id"]
            return redirect("/")
    else: 
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        id = session["user_id"]
        stock_info = lookup(request.form.get("symbol"))
        amount = float(request.form.get("shares"))
        amount_owned = db.execute("SELECT amount, id FROM stocks WHERE user_id = ? AND symbol = ?", id, request.form.get("symbol"))
        stock_id = amount_owned[0]["id"]
        amount_inceremented = stock_info["price"] * amount
        if not isinstance(amount, (float, int)):
            return apology("Please enter a number")
        if not amount_owned:
            return apology("You do not own any shares of the stock")
        if amount <= 0:
            return apology("The amount cannot be negative")
        if amount_owned[0]["amount"] < amount:
            return apology("You do not have enough shares")
        if amount_owned[0]["amount"] - amount == 0:
            db.execute("DELETE FROM stocks WHERE user_id = ? AND symbol = ? AND amount = ? AND id = ?", id, request.form.get("symbol"), amount_owned[0]["amount"], stock_id)
            db.execute("INSERT INTO history (user_id, symbol, action, amount, price) VALUES(?, ?, ?, ?, ?)", id, request.form.get("symbol"), "sell", amount, stock_info["price"])
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", amount_inceremented, id)

            return redirect("/")
        db.execute("UPDATE stocks SET amount = amount - ? WHERE user_id = ? AND symbol = ? AND id = ?", amount, id, request.form.get("symbol"), stock_id)
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", amount_inceremented, id)
        db.execute("INSERT INTO history (user_id, symbol, action, amount, price) VALUES(?, ?, ?, ?, ?)", id, request.form.get("symbol"), "sell", amount, stock_info["price"])

        return redirect("/")
    else:
        return render_template("sell.html")