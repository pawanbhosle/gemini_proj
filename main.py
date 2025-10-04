from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flasgger import Swagger
from datetime import date
import openai

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://postgres:1234@localhost:5432/test_11'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SWAGGER'] = {
    "title": "E-Commerce API",
    "uiversion": 3,
    "description": "API to manage Customers, Products, Orders and Order Items (Flask + SQLAlchemy)",
    "version": "1.0.0"
}
swagger = Swagger(app)

db = SQLAlchemy(app)

class Customer(db.Model):
    __tablename__ = "customers"
    customer_id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15))
    address = db.Column(db.String(255))
    city = db.Column(db.String(50))
    state = db.Column(db.String(50))
    zip_code = db.Column(db.String(10))
    orders = db.relationship("Order", backref="customer", lazy=True)

class Product(db.Model):
    __tablename__ = "products"
    product_id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    price = db.Column(db.Numeric, nullable=False)
    stock_quantity = db.Column(db.Integer, nullable=False)
    order_items = db.relationship("OrderItem", backref="product", lazy=True)

class Order(db.Model):
    __tablename__ = "orders"
    order_id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"), nullable=False)
    order_date = db.Column(db.Date, nullable=False)
    total_amount = db.Column(db.Numeric, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    items = db.relationship("OrderItem", backref="order", lazy=True)

class OrderItem(db.Model):
    __tablename__ = "order_items"
    order_item_id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.order_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric, nullable=False)
with app.app_context():
    db.create_all()

# ------------------ ORDER ROUTES ------------------
@app.route("/orders", methods=["POST"])
def create_order():
    """
    Create a new order
    ---
    tags:
      - Orders
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        description: JSON payload to create an order
        schema:
          type: object
          required:
            - customer_id
            - order_date
            - items
          properties:
            customer_id:
              type: integer
              example: 1
            order_date:
              type: string
              example: "2025-10-05"
            items:
              type: array
              items:
                type: object
                required:
                  - product_id
                  - quantity
                properties:
                  product_id:
                    type: integer
                    example: 1
                  quantity:
                    type: integer
                    example: 2
    responses:
      201:
        description: Order created successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Order created"
            order_id:
              type: integer
              example: 10
      400:
        description: Invalid input or stock issue
    """
    data = request.get_json()
    customer_id = data.get("customer_id")
    order_date_str = data.get("order_date")
    items = data.get("items")

    # Validations
    if not customer_id or not order_date_str or not items:
        return jsonify({"error": "customer_id, order_date, and items are required"}), 400

    if len(items) > 5:
        return jsonify({"error": "Cannot add more than 5 items per order"}), 400

    order_date_obj = date.fromisoformat(order_date_str)
    if order_date_obj < date.today():
        return jsonify({"error": "Order date cannot be in the past"}), 400

    total_amount = 0
    for item in items:
        product = Product.query.get(item["product_id"])
        if not product:
            return jsonify({"error": f"Product {item['product_id']} not found"}), 400
        if product.stock_quantity < item["quantity"]:
            return jsonify({"error": f"Insufficient stock for {product.product_name}"}), 400
        total_amount += product.price * item["quantity"]

    new_order = Order(customer_id=customer_id, order_date=order_date_obj, total_amount=total_amount)
    db.session.add(new_order)
    db.session.flush()  # get order_id

    for item in items:
        product = Product.query.get(item["product_id"])
        order_item = OrderItem(order_id=new_order.order_id,
                               product_id=product.product_id,
                               quantity=item["quantity"],
                               price=product.price)
        product.stock_quantity -= item["quantity"]
        db.session.add(order_item)

    db.session.commit()
    return jsonify({"message": "Order created", "order_id": new_order.order_id}), 201

@app.route("/orders/<int:order_id>", methods=["DELETE"])
def delete_order(order_id):
    """
    Delete an order
    ---
    tags:
      - Orders
    parameters:
      - name: order_id
        in: path
        required: true
        schema:
          type: integer
    responses:
      200:
        description: Order deleted
      404:
        description: Order not found
    """
    order = Order.query.get(order_id)
    if not order:
        return jsonify({"error": "Order not found"}), 404

    for item in order.items:
        product = Product.query.get(item.product_id)
        product.stock_quantity += item.quantity
        db.session.delete(item)

    db.session.delete(order)
    db.session.commit()
    return jsonify({"message": "Order deleted successfully"}), 200

# ------------------ GENERATIVE AI ROUTE ------------------
openai.api_key = "AIzaSyBepHw5xcbD960zlbxHtlWdUEzYfFVr_kQ"

@app.route("/genai-query", methods=["POST"])
def genai_query():
    """
    Execute natural language query via Generative AI
    ---
    tags:
      - GenAI
    consumes:
      - application/json
    parameters:
      - in: body
        name: body
        required: true
        description: Natural language query to convert into SQL
        schema:
          type: object
          required:
            - query
          properties:
            query:
              type: string
              example: "Find products that are out of stock"
    responses:
      200:
        description: SQL query executed successfully
        schema:
          type: object
          properties:
            sql:
              type: string
              example: "SELECT * FROM products WHERE stock_quantity = 0;"
            result:
              type: array
              items:
                type: object
      400:
        description: Invalid query
    """
    data = request.get_json()
    user_query = data.get("query")
    if not user_query:
        return jsonify({"error": "Query is required"}), 400

    prompt = f"Convert this natural language query into SQL for tables Customers, Products, Orders, Order_Items:\n{user_query}\nSQL:"

    try:
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            max_tokens=150
        )
        sql_query = response.choices[0].text.strip()
        result = db.session.execute(sql_query).fetchall()
        result_json = [dict(row._mapping) for row in result]
        return jsonify({"sql": sql_query, "result": result_json}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ------------------ TEST ROUTE ------------------
@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"message": "pong"})

# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True)
