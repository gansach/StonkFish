import os
import datetime

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get users current cash
    cash = (db.execute("SELECT cash FROM users WHERE id = :user_id",
                      user_id=session["user_id"]))[0]["cash"]
    # Get users holdings
    rows = db.execute("SELECT * FROM holdings WHERE user_id = :user_id ORDER BY symbol ASC",
                     user_id=session["user_id"])
    total = 0
    for row in rows:
        company_details = lookup(row["symbol"])
        price = company_details["price"]
        value = price * row["stocks"]
        row["name"] = company_details["name"]
        row["price"] = usd(price)
        row["value"] = usd(value)
        total += value
    return render_template("index.html", holdings=rows, cash=usd(cash), total=usd(total + cash))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST
    if request.method == "POST":

        # Ensure stock was submitted
        if not request.form.get("symbol"):
            return apology("Stock name is required", 403)

        # Ensure stock is valid
        elif not bool(lookup(request.form.get("symbol"))):
            return apology("Enter valid stock name", 403)

        else:

            # Ensure positive number of stocks
            try:
                if int(request.form.get("shares")) < 0:
                    return apology("Enter valid number of shares", 403)
            except ValueError:
                return apology("Enter valid number of shares", 403)

            symbol = request.form.get("symbol")
            stocks = int(request.form.get("shares"))
            price = lookup(symbol.upper())["price"]
            rows = db.execute("SELECT cash FROM users WHERE id = :user_id",
                              user_id = session["user_id"])
            cash = rows[0]["cash"]
            date_time = str(datetime.datetime.now())

            # Ensure user has enough cash to purchase
            if price * stocks > cash:
                return apology("Unable to purchase: cannot afford", 403)


            else:

                # Add new transaction to history database
                db.execute("INSERT INTO history (user_id, symbol, stocks, price, datetime) VALUES (:user_id, :symbol, :stocks, :price, :date_time)",
                          user_id=session["user_id"], symbol=symbol, stocks=stocks, price=price * stocks, date_time=date_time )

                # Get users holdings
                holdings = db.execute("SELECT * FROM holdings WHERE user_id = :user_id AND symbol = :symbol",
                                     user_id=session["user_id"], symbol=symbol.upper())

                # Update existing holding
                if bool(holdings):
                    new_stocks = holdings[0]["stocks"] + stocks
                    db.execute("UPDATE holdings SET stocks = :new_stocks WHERE user_id = :user_id AND symbol = :symbol",
                              new_stocks = new_stocks, user_id = session["user_id"], symbol = symbol.upper())

                # Add new holding
                else:
                    db.execute("INSERT INTO holdings (user_id, symbol, stocks) VALUES (:user_id, :symbol, :stocks)",
                              user_id=session["user_id"], symbol=symbol, stocks=stocks)

                # Update user's cash
                db.execute("UPDATE users SET cash = :cash_new WHERE id = :user_id",
                          cash_new = cash - (price * stocks), user_id = session["user_id"])

                # Redirect user to homepage
                return redirect("/")


    # User reached route via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    history = db.execute("SELECT * FROM history WHERE user_id = :user_id", user_id=session["user_id"])

    for row in history:
        row["price"] = usd(row["price"])
        row["datetime"] = row["datetime"][:19]
    return render_template("history.html", history = history)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
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
    """Search a stock"""

    # User reached route via POST
    if request.method == "POST":
        symbol = request.form.get('symbol')
        stock_dict = lookup(symbol.upper())

        # Ensure Stock is valid
        if not bool(stock_dict):
            return apology("Stock not found", 404)
        else:
            stock_dict["price"] = usd(stock_dict["price"])
            return render_template("quoted.html", stock_dict = stock_dict)

    # User reached route via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register new user"""

    # User reached route via POST (i.e user registerred)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get('username'):
            return apology("must provide username", 403)

        # Ensure passord was submitted
        elif not request.form.get('password') or not request.form.get('confirm'):
            return apology("must confirm password", 403)

        # Ensure password was confirmed
        elif request.form.get('password') != request.form.get('confirm'):
            return apology("passowords don't match", 403)

        else:
            # Ensure username does not already exist
            if bool(db.execute("SELECT * FROM users WHERE username = :username",
                               username = request.form.get('username'))):
                return apology("username already exists", 403)

            # Insert new user to database
            else:
                pass_hash = generate_password_hash(request.form.get('password'))
                db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)",
                           username = request.form.get('username'), hash = pass_hash)
                return redirect("/")

    # User reached route via GET
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get users holdings
    holdings = db.execute("SELECT symbol,stocks FROM holdings WHERE user_id = :user_id ORDER BY symbol ASC",
                             user_id = session["user_id"])

    # User reached via route POST
    if request.method == "POST":

        # Ensure stock was submitted
        if not request.form.get("symbol"):
            return apology("No stock selected", 403)

        # Ensure user owns entered stock
        elif request.form.get("symbol") not in [row["symbol"] for row in holdings]:
            return apology("TODO")

        # Ensure user entered shares
        elif not request.form.get("shares"):
            return apology("Must enter shares")

        else:

            # Ensure positive number of shares
            try:
                if int(request.form.get("shares")) < 0:
                    return apology("Enter valid number of shares", 403)
            except ValueError:
                return apology("Enter valid number of shares", 403)

            # Ensure user owns enough shares
            symbol = request.form.get("symbol")
            shares = (db.execute("SELECT stocks FROM holdings WHERE user_id = :user_id AND symbol = :symbol",
                               user_id = session["user_id"], symbol = symbol))[0]["stocks"]

            if int(request.form.get("shares")) > shares:
                return apology("Too many shares")

            else:
                price = lookup(symbol.upper())["price"]
                date_time = str(datetime.datetime.now())
                rows = db.execute("SELECT cash FROM users WHERE id = :user_id",
                              user_id = session["user_id"])
                cash = rows[0]["cash"]
                shares_sold = int(request.form.get("shares"))

                # Enter transaction to history database
                db.execute("INSERT INTO history (user_id, symbol, stocks, price, datetime) VALUES (:user_id, :symbol, :stocks, :price, :date_time)",
                          user_id=session["user_id"], symbol=symbol, stocks=-shares_sold, price=price * shares_sold, date_time=date_time )

                # Update holding
                new_stocks = shares - int(request.form.get("shares"))
                db.execute("UPDATE holdings SET stocks = :new_stocks WHERE user_id = :user_id AND symbol = :symbol",
                          new_stocks = new_stocks, user_id = session["user_id"], symbol = symbol.upper())

                if new_stocks == 0:
                    db.execute("DELETE FROM holdings WHERE stocks = 0;")

                # Update user's cash
                db.execute("UPDATE users SET cash = :cash_new WHERE id = :user_id",
                          cash_new = cash + (price * shares_sold), user_id = session["user_id"])

                # Redirect user to homepage
                return redirect("/")

    # User reaced via route GET
    else:
        return render_template("sell.html", holdings = holdings)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
