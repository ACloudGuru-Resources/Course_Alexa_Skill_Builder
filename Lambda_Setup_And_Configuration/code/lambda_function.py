import logging
import json
import os
import boto3
import requests
from random import randint
import datetime as dt
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

#from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.skill_builder import CustomSkillBuilder
from ask_sdk_core.api_client import DefaultApiClient
from ask_sdk_core.dispatch_components import AbstractRequestHandler
from ask_sdk_core.dispatch_components import AbstractExceptionHandler
from ask_sdk_core.dispatch_components import AbstractResponseInterceptor
from ask_sdk_core.dispatch_components import AbstractRequestInterceptor
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_core.exceptions import AskSdkException
import ask_sdk_core.utils as ask_utils

logger = logging.getLogger()
#retrieve logging level from lambda environmet properties
level = os.environ['LOG_LEVEL']
logger.setLevel(int(level))

WELCOME_MESSAGE = "Unleash your inner adventurer and explore the " \
    " world and way beyond. On your adventure, <break time='1s'/> you start with " \
     "<prosody volume='x-loud'> a lot </prosody> of money and energy. " \
    "But the choices you make will either increase or decrease them. " \
    "Your adventure ends when you either run out of money or energy. " \
    "<say-as interpret-as='interjection'>Stay on your adventure as long as you can</say-as><break time='1s'/> before it ends! " \
    "Start by saying visit <voice name='Giorgio'>Italy</voice> or visit <voice name='Nicole'>Australia</voice>"

VISIT_COUNTRY_REPROMPT = "Do you want to visit <voice name=\"Giorgio\">Italy</voice> or <voice name=\"Nicole\">Australia</voice>?"
YES_OR_N0_REPROMPTS = ['Do not stall adventurer! Please answer yes or no. If you need a travel tip, say speak to the guide.','Be careful adventurer, is your answer yes or no.','You are running out of time adventurer! Please answer yes or no.','Adventurer, is your answer yes or no. If you need a travel tip, say speak to the guide.','Yes or No, adventurer! If you need a travel tip, say speak to the guide.']
GAME_END = "The next question could not be found for your adventure. You have reached the end."

#Handler for skill launch with no intent
class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In LaunchRequestHandler")
        response_builder = handler_input.response_builder

        speak_output = WELCOME_MESSAGE
        reprompt_output = VISIT_COUNTRY_REPROMPT 

        return (
            response_builder
                .speak(speak_output)  #the spoken output to the user
                .ask(reprompt_output) #add a reprompt if you want to keep the session open for the user to respond; only one reprompt allowed
                .response
        )


####### Custom Intent Handlers########
class StartAdventureIntentHandler(AbstractRequestHandler):
    """Handler for Start Adventure intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("StartAdventureIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        logger.info("In StartAdventureIntentHandler")
        response_builder = handler_input.response_builder
        speak_output = WELCOME_MESSAGE
        reprompt_output = VISIT_COUNTRY_REPROMPT

        return (
            response_builder
                .speak(speak_output)  #the spoken output to the user
                .ask(reprompt_output) #add a reprompt if you want to keep the session open for the user to respond; only one reprompt allowed
                .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    """Handler for Help Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Hello, adventurer! It's good to see you! Your wealth or energy either increase or decrease based on the choices " 
        "you make while on your adventure. When you run out of either, the game ends. " 
        "To start your adventure, say visit Italy or Australia." 

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(speak_output)
                .response
        )


class CancelOrStopIntentHandler(AbstractRequestHandler):
    """Single handler for Cancel and Stop Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return (ask_utils.is_intent_name("AMAZON.CancelIntent")(handler_input) or
                ask_utils.is_intent_name("AMAZON.StopIntent")(handler_input))

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speak_output = "Goodbye!"
        speak_output = speak_output + " New adventures to Egypt, England, and Greece coming soon!"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )

class FallbackIntentHandler(AbstractRequestHandler):
    
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        speech = (
                "Sorry. I cannot help with that. I can help you "
                "continue on your adventure by saying visit Italy or vist Australia. "
            )
        reprompt = "I didn't catch that. What can I help you with?"

        return handler_input.response_builder.speak(speech).ask(
            reprompt).response

class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        # Any cleanup logic goes here.

        return handler_input.response_builder.response

class CatchAllExceptionHandler(AbstractExceptionHandler):
    """Generic error handling to capture any syntax or routing errors."""
    def can_handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> bool
        return True

    def handle(self, handler_input, exception):
        # type: (HandlerInput, Exception) -> Response
        logger.error(exception, exc_info=True)
        logger(handler_input)

        speak_output = "Sorry, I had trouble doing what you asked. Please try again."

        return (
            handler_input.response_builder
                .speak(speak_output)
                .ask(speak_output)
                .response
        )

class LoggingResponseInterceptor(AbstractResponseInterceptor):
    """Invoked immediately after execution of the request handler for an incoming request. 
    Used to print response for logging purposes
    """
    def process(self, handler_input, response):
         # type: (HandlerInput, Response) -> None
        logger.debug("Response logged by LoggingResponseInterceptor: {}".format(response))

class LoggingRequestInterceptor(AbstractRequestInterceptor):
    """Invoked immediately before execution of the request handler for an incoming request. 
    Used to print request for logging purposes
    """
    def process(self, handler_input):
        logger.debug("Request received by LoggingRequestInterceptor: {}".format(handler_input.request_envelope))

# The SkillBuilder object acts as the entry point for your skill, routing all request and response
# payloads to the handlers above. Make sure any new handlers or interceptors you've
# defined are included below. The order matters - they're processed top to bottom.

# Skill Builder object
sb = CustomSkillBuilder(api_client=DefaultApiClient())

# Add all request handlers to the skill.
sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(StartAdventureIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(CancelOrStopIntentHandler())
sb.add_request_handler(SessionEndedRequestHandler())
sb.add_request_handler(FallbackIntentHandler())

# Add exception handler to the skill.
sb.add_exception_handler(CatchAllExceptionHandler())

# Add request and response interceptors
sb.add_global_response_interceptor(LoggingResponseInterceptor())
sb.add_global_request_interceptor(LoggingRequestInterceptor())

# Expose the lambda handler function that can be tagged to AWS Lambda handler
handler = sb.lambda_handler()