
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import db_helper
import generic_helper
import logging

app = FastAPI()
logging.basicConfig(level=logging.INFO)

inprogress_orders = {}

@app.post("/")
async def handle_request(request: Request):
    try:
        payload = await request.json()
        intent = payload['queryResult']['intent']['displayName']
        parameters = payload['queryResult']['parameters']
        output_contexts = payload['queryResult']['outputContexts']
        session_id = generic_helper.extract_session_id(output_contexts[0]["name"])

        intent_handler_dict = {
            'order.add - context: ongoing-order': add_to_order,
            'order.remove - context: ongoing-order': remove_from_order,
            'order.complete - context: ongoing-order': complete_order,
            'track.order - context: ongoing-tracking': track_order
        }

        if intent in intent_handler_dict:
            return await intent_handler_dict[intent](parameters, session_id)
        else:
            return JSONResponse(content={
                "fulfillmentText": "Sorry, I didn't understand that intent."
            })
    except Exception as e:
        logging.error(f"Error handling request: {e}")
        return JSONResponse(content={
            "fulfillmentText": "An error occurred while processing your request. Please try again."
        })

def save_to_db(order: dict):
    try:
        logging.info("Starting to save order to database.")
        next_order_id = db_helper.get_next_order_id()
        logging.info(f"Next order ID: {next_order_id}")
        for food_item, quantity in order.items():
            rcode = db_helper.insert_order_item(food_item, quantity, next_order_id)
            if rcode == -1:
                logging.error(f"Failed to insert order item: {food_item} with quantity: {quantity}")
                raise Exception("Failed to insert order item into database")
            logging.info(f"Inserted order item: {food_item} with quantity: {quantity}")
        
        db_helper.insert_order_tracking(next_order_id, "in progress")
        logging.info(f"Order tracking inserted for order ID: {next_order_id}")
        return next_order_id
    except Exception as e:
        logging.error(f"Error saving to database: {e}")
        return -1

async def complete_order(parameters: dict, session_id: str):
    try:
        if session_id not in inprogress_orders:
            fulfillment_text = "I'm having trouble finding your order. Sorry! Can you place a new order please?"
        else:
            order = inprogress_orders[session_id]
            order_id = save_to_db(order)
            if order_id == -1:
                fulfillment_text = "Sorry, I couldn't process your order due to a backend error. Please place a new order again"
            else:
                order_total = db_helper.get_total_order_price(order_id)
                fulfillment_text = f"Awesome. We have placed your order. Here is your order id # {order_id}. Your order total is {order_total} which you can pay at the time of delivery!"
            del inprogress_orders[session_id]

        return JSONResponse(content={
            "fulfillmentText": fulfillment_text
        })
    except Exception as e:
        logging.error(f"Error completing order: {e}")
        return JSONResponse(content={
            "fulfillmentText": "An error occurred while completing your order. Please try again."
        })

async def add_to_order(parameters: dict, session_id: str):
    try:
        food_items = parameters["food-item"]
        quantities = parameters["number"]
        if len(food_items) != len(quantities):
            fulfillment_text = "Sorry I didn't understand. Can you please specify food items and quantities clearly?"
        else:
            new_food_dict = dict(zip(food_items, quantities))
            if session_id in inprogress_orders:
                current_food_dict = inprogress_orders[session_id]
                current_food_dict.update(new_food_dict)
                inprogress_orders[session_id] = current_food_dict
            else:
                inprogress_orders[session_id] = new_food_dict

            order_str = generic_helper.get_str_from_food_dict(inprogress_orders[session_id])
            fulfillment_text = f"So far you have: {order_str}. Do you need anything else?"

        return JSONResponse(content={
            "fulfillmentText": fulfillment_text
        })
    except Exception as e:
        logging.error(f"Error adding to order: {e}")
        return JSONResponse(content={
            "fulfillmentText": "An error occurred while adding items to your order. Please try again."
        })

async def remove_from_order(parameters: dict, session_id: str):
    try:
        if session_id not in inprogress_orders:
            return JSONResponse(content={
                "fulfillmentText": "I'm having trouble finding your order. Sorry! Can you place a new order please?"
            })

        food_items = parameters["food-item"]
        current_order = inprogress_orders[session_id]

        removed_items = []
        no_such_items = []

        for item in food_items:
            if item not in current_order:
                no_such_items.append(item)
            else:
                removed_items.append(item)
                del current_order[item]

        fulfillment_text = ""

        if len(removed_items) > 0:
            fulfillment_text += f'Removed {", ".join(removed_items)} from your order. '

        if len(no_such_items) > 0:
            fulfillment_text += f'The items {", ".join(no_such_items)} are not in your current order. '

        if len(current_order.keys()) == 0:
            fulfillment_text += "Your order is now empty!"
        else:
            order_str = generic_helper.get_str_from_food_dict(current_order)
            fulfillment_text += f"Here is what is left in your order: {order_str}. Do you need anything else ?"

        return JSONResponse(content={
            "fulfillmentText": fulfillment_text
        })
    except Exception as e:
        logging.error(f"Error removing from order: {e}")
        return JSONResponse(content={
            "fulfillmentText": "An error occurred while removing items from your order. Please try again."
        })

async def track_order(parameters: dict, session_id: str):
    try:
        order_id = int(parameters.get('number'))
        order_status = db_helper.get_order_status(order_id)
        if order_status:
            fulfillment_text = f"The order status for order id: {order_id} is: {order_status}"
        else:
            fulfillment_text = f"No order found with order id: {order_id}"

        return JSONResponse(content={
            "fulfillmentText": fulfillment_text
        })
    except Exception as e:
        logging.error(f"Error tracking order: {e}")
        return JSONResponse(content={
            "fulfillmentText": "An error occurred while tracking your order. Please try again."
        })
