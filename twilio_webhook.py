from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)


@app.route("/sms", methods=["POST"])
def receive_sms():

    # Number that sent the SMS
    from_number = request.form.get("From")

    # Your Twilio number
    to_number = request.form.get("To")

    # Actual SMS text
    message_body = request.form.get("Body")

    # Twilio Message SID
    message_sid = request.form.get("MessageSid")

    print("================================")
    print("Incoming SMS")
    print("From:", from_number)
    print("To:", to_number)
    print("Message:", message_body)
    print("Message SID:", message_sid)
    print("================================")

    # Create Twilio response
    response = MessagingResponse()

    response.message(
        "Thank you! We received your message."
    )

    return str(response)


# @app.route("/sms", methods=["POST"])
# def receive_sms():

#     from_number = request.form.get("From")
#     body = request.form.get("Body", "").strip().upper()

#     print("Patient:", from_number)
#     print("Response:", body)

#     response = MessagingResponse()

#     if body == "C":
#         # TODO: update appointment in your database
#         response.message(
#             "Thank you! Your dental appointment has been confirmed."
#         )

#     elif body == "R":
#         # TODO: mark appointment as needing rescheduling
#         response.message(
#             "We've received your reschedule request. "
#             "Our office will contact you shortly."
#         )

#     else:
#         response.message(
#             "Please reply C to confirm or R to reschedule."
#         )

#     return str(response)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)