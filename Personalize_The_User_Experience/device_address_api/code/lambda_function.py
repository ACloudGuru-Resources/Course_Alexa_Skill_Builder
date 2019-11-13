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
from ask_sdk_core.response_helper import get_plain_text_content
from ask_sdk_model.ui import SimpleCard
from ask_sdk_model import ui
from ask_sdk_model.interfaces.display import (
    ImageInstance, Image, RenderTemplateDirective,
    BackButtonBehavior, BodyTemplate2)
from ask_sdk_model import Response
from ask_sdk_core.exceptions import AskSdkException
import ask_sdk_core.utils as ask_utils
from ask_sdk_model.interfaces.alexa.presentation.apl import (
    RenderDocumentDirective)
from ask_sdk_core.utils import viewport, is_request_type
from ask_sdk_model.services.monetization import (
    EntitledState, PurchasableState, InSkillProductsResponse, Error,
    InSkillProduct)
from ask_sdk_model.interfaces.monetization.v1 import PurchaseResult
from ask_sdk_model.interfaces.connections import SendRequestDirective

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
        logger.info("The user's country is {} ".format(get_user_country(handler_input)))
        response_builder = handler_input.response_builder
        include_display(handler_input)

        #is returning user
        if is_returning_user(handler_input):
            #if active adventure; welcome back to adventure
            if has_active_adventure(handler_input):
                #retrieve current stats
                speak_output = continue_adventure(handler_input) 
                reprompt_output = YES_OR_N0_REPROMPTS[randint(0, len(YES_OR_N0_REPROMPTS)-1)]  
            else:
                speak_output = "Welcome back, adventurer! You don't have an active adventure. " + VISIT_COUNTRY_REPROMPT
                reprompt_output = VISIT_COUNTRY_REPROMPT
        else:
            add_new_user(handler_input.request_envelope.context.system)
            speak_output = WELCOME_MESSAGE
            reprompt_output = VISIT_COUNTRY_REPROMPT

        return response_builder.speak(speak_output).ask(reprompt_output).response

####### Custom Intent Handlers########
class StartAdventureIntentHandler(AbstractRequestHandler):
    """Handler for Start Adventure intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("StartAdventureIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        response_builder = handler_input.response_builder
        include_display(handler_input)

        try:
            #if user is already on the session, find current adventure stats and ask the next Yes/No question
            if is_user_on_session(handler_input):
                speak_output = continue_adventure(handler_input)  
                reprompt_output = YES_OR_N0_REPROMPTS[randint(0, len(YES_OR_N0_REPROMPTS)-1)] 
            else: #if user is not on session are they a new user or do they have an active adventure
                #is new user
                if is_returning_user(handler_input):
                    #find current adventure stats and ask the next Yes/No question
                    #if active adventure; welcome back to adventure
                    if has_active_adventure(handler_input):
                        speak_output = continue_adventure(handler_input)
                        reprompt_output = YES_OR_N0_REPROMPTS[randint(0, len(YES_OR_N0_REPROMPTS)-1)] 
                    else:
                        start_new_adventure(handler_input) 
                        speak_output = get_next_question(handler_input.attributes_manager.session_attributes["country"],handler_input.attributes_manager.session_attributes["stats_record"],handler_input)  

                        #Determine country and play correct audio via SSML
                        if handler_input.attributes_manager.session_attributes["country"] == 'Italy':
                            speak_output = "<audio src=\"https://d1yy08fpd1djho.cloudfront.net/italyc.mp3\" /> <voice name=\"Giorgio\">Welcome to your new Italian adventure!</voice> " + speak_output 
                        elif handler_input.attributes_manager.session_attributes["country"] == 'Australia':
                            speak_output = "<audio src=\"https://d1yy08fpd1djho.cloudfront.net/australiac.mp3\" /><voice name=\"Nicole\"> Welcome to your new Australian adventure!</voice> " + speak_output 
                        reprompt_output = YES_OR_N0_REPROMPTS[randint(0, len(YES_OR_N0_REPROMPTS)-1)]  
                else:
                    add_new_user(handler_input.request_envelope.context.system)
                    #ask if they want 
                    speak_output = WELCOME_MESSAGE
                    reprompt_output = VISIT_COUNTRY_REPROMPT
        except:
            logger.error("An error in StartAdventureIntentHandler for text type {} ".format(handler_input)) 
            speak_output = "Sorry, adventurer! I don't understand what you want to do. That country is probably not supported yet. {}".format(VISIT_COUNTRY_REPROMPT)
            reprompt_output = VISIT_COUNTRY_REPROMPT

        return (
            response_builder
                .speak(speak_output)
                .ask(reprompt_output) #add a reprompt if you want to keep the session open for the user to respond
                .response
        )

####### Built-in Intent Handlers With Custom Code########
class YesIntentHandler(AbstractRequestHandler):
    """Handler for Yes Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.YesIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        response_builder = handler_input.response_builder
        include_display(handler_input)
        
        # retrieve response to user from database 
        speak_output = getYesorNoResponse(handler_input, 'YesResponseText') 
        
        try:
            if is_game_over(handler_input.attributes_manager.session_attributes["stats_record"]) == False:
                reprompt_output = YES_OR_N0_REPROMPTS[randint(0, len(YES_OR_N0_REPROMPTS)-1)]
                handler_input.response_builder.ask(reprompt_output)
        except:
            logger.error("An error in YesIntentHandler {}".format(handler_input)) 
            speak_output = "Sorry, adventurer! I don't understand what you want to do. {} If so, say visit Italy or Australia.".format(VISIT_COUNTRY_REPROMPT)

        return (
            response_builder
                .speak(speak_output)
                .response
        )

class NoIntentHandler(AbstractRequestHandler):
    """Handler for No Intent."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_intent_name("AMAZON.NoIntent")(handler_input)
        
    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        response_builder = handler_input.response_builder
        include_display(handler_input)

        speak_output = getYesorNoResponse(handler_input, 'NoResponseText')

        try:
            if is_game_over(handler_input.attributes_manager.session_attributes["stats_record"]) == False:
                reprompt_output = YES_OR_N0_REPROMPTS[randint(0, len(YES_OR_N0_REPROMPTS)-1)]
                handler_input.response_builder.ask(reprompt_output)
        except:
            logger.error("An error in NoIntentHandler {}".format(handler_input)) 
            speak_output = "Sorry, adventurer! I don't understand what you want to do. {} If so, say visit Italy or Australia.".format(VISIT_COUNTRY_REPROMPT)

        return (
            response_builder
                .speak(speak_output)
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

        response_builder = handler_input.response_builder
        include_display(handler_input)

        return (
            response_builder
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
        speak_output = "Goodbye!" + getRandomFact() + ". New adventures to Egypt, England, and Greece coming soon!"
        response_builder = handler_input.response_builder
        include_display(handler_input)

        return (
            response_builder
                .speak(speak_output)
                .response
        )

class FallbackIntentHandler(AbstractRequestHandler):
    
    def can_handle(self, handler_input):
        return ask_utils.is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response
        response_builder = handler_input.response_builder
        include_display(handler_input)

        speech = (
                "Sorry. I cannot help with that. I can help you "
                "continue on your adventure by saying visit Italy or vist Australia. "
            )
        reprompt = "I didn't catch that. What can I help you with?"

        return response_builder.speak(speech).ask(reprompt).response

class SessionEndedRequestHandler(AbstractRequestHandler):
    """Handler for Session End."""
    def can_handle(self, handler_input):
        # type: (HandlerInput) -> bool
        return ask_utils.is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input):
        # type: (HandlerInput) -> Response

        updateStats(handler_input)
        speak_output = "Goodbye!" + getRandomFact() + ". New adventures to Egypt, England, and Greece coming soon!"

        return (
            handler_input.response_builder
                .speak(speak_output)
                .response
        )

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

#---------------general utility functions---------------------
#get random fact on SessionEnd, Cancel, or Stop
def getRandomFact():
    record_number = randint(1,5)
    table = boto3.resource('dynamodb').Table('AdvgFunFacts')
    fact_record = table.query(KeyConditionExpression=Key('RecordNumber').eq(str(record_number))) # dynamo is case-sensitive

    if fact_record['Count'] == 1:
        return fact_record['Items'][0]['Text']
    else:
        logger.error("Cannot find fun fact record") 
        return "Egypt is known for its longest history among the modern nations."

def getYesorNoResponse(handler_input, textType):
    #retrieve the questions details
    table = boto3.resource('dynamodb').Table('AdvgStoryDetails')
    speak_output = GAME_END

    try: 
        #retrieve the Yes or No response for the question
        question_record = table.query(KeyConditionExpression=Key('CountryId').eq(get_country_id(handler_input.attributes_manager.session_attributes["country"])) &
        Key('QuestionNumber').eq(handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['QuestionNumber']+1)) 

        #record found
        if question_record['Count'] == 1: 
            #speak the Yes or No details
            speak_output = question_record['Items'][0][textType]
            speak_output = "<voice name=\""+ get_polly_voice(handler_input.attributes_manager.session_attributes["country"]) + "\">" + speak_output + " </voice>"

            #increase current turns by 1 in session
            handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['CurrentTurns'] += 1 
            
            #increase completed question number in session
            handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['QuestionNumber'] += 1

            #actually add to or delete from energy/wealth levels in session
            if textType == 'YesResponseText':
                handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['MoneyLevel'] += question_record['Items'][0]['YesWealthImpact']
                handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['EnergyLevel'] += question_record['Items'][0]['YesEnergyImpact']
            elif textType == 'NoResponseText':
                handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['MoneyLevel'] += question_record['Items'][0]['NoWealthImpact']
                handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['EnergyLevel'] += question_record['Items'][0]['NoEnergyImpact']   

            #determine if the game needs to end; ends if player runs out of health or wealth
            current_wealth = handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['MoneyLevel']
            current_energy = handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['EnergyLevel']

            #you are out of wealth or health -- the game is over
            if is_game_over(handler_input.attributes_manager.session_attributes["stats_record"]):
                speak_output = "<voice name=\""+ get_polly_voice(handler_input.attributes_manager.session_attributes["country"]) + "\">Oh no adventurer, you don't have enough wealth or energy to continue on your adventure! This means your adventure is over. </voice> " 
                #update Game Stats to end the game by setting flag to N
                set_game_flag('N', handler_input)
            #if they are low on wealth/health -- they need a warning
            elif is_warning_needed(current_wealth,current_energy):
                speak_output = "<voice name=\""+ get_polly_voice(handler_input.attributes_manager.session_attributes["country"]) + "\">Be careful adventurer, you are running low on wealth or energy. If you need a travel tip, say speak to the guide.</voice> " 
                speak_output = speak_output + " " + get_next_question(handler_input.attributes_manager.session_attributes["country"], handler_input.attributes_manager.session_attributes["stats_record"],handler_input)
            else: 
                speak_output = speak_output + " " + get_next_question(handler_input.attributes_manager.session_attributes["country"], handler_input.attributes_manager.session_attributes["stats_record"],handler_input)   
        else: #record not found
            logger.error("That question number doesn't exist: {}".format(handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['QuestionNumber'])) 
            # raise AskSdkException("That question number doesn't exist: {}".format(handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['QuestionNumber'])) 
    except:
        logger.error("An error in getYesorNoResponse for text type {} -- {}".format(textType,handler_input)) 
        speak_output = "Sorry, adventurer! I don't understand what you want to do. {}".format(VISIT_COUNTRY_REPROMPT)

    return speak_output 

def updateStats(handler_input):
    if is_user_on_session(handler_input) and has_active_adventure(handler_input):
        table = boto3.resource('dynamodb').Table('AdvgGameStats')
        table.update_item(
            Key={
                'PlayerNumber': handler_input.attributes_manager.session_attributes["user"]['Items'][0]['PlayerNumber'],
                'CountryId' : get_country_id(handler_input.attributes_manager.session_attributes["country"])
            },
            UpdateExpression="set EnergyLevel = :e, MoneyLevel=:m, QuestionNumber=:q, CurrentTurns=:c",
            ConditionExpression="ActiveFlag=:a",
            ExpressionAttributeValues={
                ':e': handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['EnergyLevel'],
                ':m': handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['MoneyLevel'],
                ':q': handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['QuestionNumber'],
                ':c': handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['CurrentTurns'],
                ':a': 'Y'
            },
            ReturnValues="UPDATED_NEW"
        )

        #update max turns 
        maxTurns = handler_input.attributes_manager.session_attributes["user"]['Items'][0]['MaxTurns']
        currentTurns = handler_input.attributes_manager.session_attributes["stats_record"]['Items'][0]['CurrentTurns']

        if currentTurns > maxTurns:
            table = boto3.resource('dynamodb').Table('AdvgUsers')
            table.update_item(
                Key = {
                    'UserId': handler_input.attributes_manager.session_attributes["user"]['Items'][0]['UserId'],
                    'PlayerNumber': handler_input.attributes_manager.session_attributes["user"]['Items'][0]['PlayerNumber'],
                },
                UpdateExpression="set MaxTurns = :m",
                ExpressionAttributeValues={
                    ':m': currentTurns
                }
            )

def get_user(user_id):
    table = boto3.resource('dynamodb').Table('AdvgUsers')
    user = table.query(KeyConditionExpression=Key('UserId').eq(user_id)) # dynamo is case-sensitive
    return user  

def is_returning_user(handler_input):
    user_record = get_user(handler_input.request_envelope.context.system.user.user_id)
    if user_record['Count'] == 1:
        #add user to session
        handler_input.attributes_manager.session_attributes["user"] = user_record
        return True
    else:
        return False
  
def add_new_user(system):
    table = boto3.resource('dynamodb').Table('AdvgUsers')
    date = str(dt.datetime.today().strftime("%Y-%m-%d"))
    
    table.put_item(
        Item={
            "Name": "TBD-USERAPI",
            "PlayerNumber": randint(1, 1000000000),
            "DeviceId": system.device.device_id,
            "Date": date,
            "UserId": system.user.user_id,
            "Country": "TBD-ADDRESSAPI",
            "Email": "TBD-CUSTINFOAPI",
            "MaxTurns": 0
        }
    )  # dynamo is case-sensitive

def is_user_on_session(handler_input):
    if 'country' in handler_input.attributes_manager.session_attributes:
        if 'stats_record' in handler_input.attributes_manager.session_attributes:
            return True
        else:
            return False
    else:
        return False

def has_active_adventure(handler_input):
    #get user from session
    user = handler_input.attributes_manager.session_attributes["user"]
    
    #determine if on an active adventure
    table = boto3.resource('dynamodb').Table('AdvgGameStats')
    stats_record = table.query(KeyConditionExpression=Key('PlayerNumber').eq(user['Items'][0]['PlayerNumber'])) 

    if stats_record['Count'] == 1:
        if stats_record['Items'][0]['ActiveFlag'] == 'Y':
            if 'country' not in handler_input.attributes_manager.session_attributes:
                handler_input.attributes_manager.session_attributes["country"] = get_country_name(stats_record['Items'][0]['CountryId'])
                
            if 'stats_record' not in handler_input.attributes_manager.session_attributes:
                handler_input.attributes_manager.session_attributes["stats_record"] = stats_record
            return True
        else:
            return False
    elif stats_record['Count'] > 1: #user has multiple adventures
        #find the active adventure
        for x in range(0,stats_record['Count']):
            item = stats_record['Items'][x]
            if item['ActiveFlag'] == 'Y':
                if 'country' not in handler_input.attributes_manager.session_attributes:
                    handler_input.attributes_manager.session_attributes["country"] =  get_country_name(item['CountryId'])
                
                if 'stats_record' not in handler_input.attributes_manager.session_attributes:
                    handler_input.attributes_manager.session_attributes["stats_record"] = stats_record['Items'][x]
                return True
        #if no active adventure, return false
        return False
    else:
        return False

def get_country_name(CountryId):
    table = boto3.resource('dynamodb').Table('AdvgCountries')
    country_record = table.query(KeyConditionExpression=Key('CountryId').eq(CountryId)) # dynamo is case-sensitive

    if country_record['Count'] == 1:
        return country_record['Items'][0]['Name']
    else:
        logger.error("Cannot find country name for given id {}".format(CountryId)) 
        raise AskSdkException("Cannot find country name for given id {}".format(CountryId)) 

def get_country_id(CountryName):
    table = boto3.resource('dynamodb').Table('AdvgCountries')
    country_record = table.query(
        IndexName='Name-index',
        KeyConditionExpression=Key('Name').eq(CountryName)) # dynamo is case-sensitive
    
    if country_record['Count'] == 1:
        return country_record['Items'][0]['CountryId']
    else:
        logger.error("Cannot find country id for given name {}".format(CountryName)) 
        raise AskSdkException("Cannot find country id for given name {}".format(CountryName)) 

def continue_adventure(handler_input):
    speak_output = "<voice name=\""+ get_polly_voice(handler_input.attributes_manager.session_attributes["country"]) + "\">Welcome back adventurer! It's good to see you!</voice> " 

    speak_output = speak_output + get_next_question(handler_input.attributes_manager.session_attributes["country"], handler_input.attributes_manager.session_attributes["stats_record"],handler_input)  

    return speak_output
    
def get_next_question(countryname, stats, handler_input):
    #return next question
    table = boto3.resource('dynamodb').Table('AdvgStories')
    speak_output = GAME_END
    
    #retrieve the next question for the particular country
    question_record = table.query(KeyConditionExpression=Key('CountryId').eq(get_country_id(countryname)) &
    Key('QuestionNumber').eq(stats['Items'][0]['QuestionNumber']+1)) #current completed question + 1

    #record found
    if question_record['Count'] == 1: 
        speak_output = question_record['Items'][0]['QuestionText']    
    else: #record not found
        logger.error("That question number doesn't exist: {}".format(stats['Items'][0]['QuestionNumber']+1)) 
        updateStats(handler_input) #current values
        set_game_flag('N', handler_input) #flag game as over
        stats['Items'][0]['ActiveFlag'] = 'N' #update value on session
        #raise AskSdkException("That question number doesn't exist: {}".format(stats['Items'][0]['QuestionNumber']+1)) 

    return speak_output

#get correct Polly voice based on selected country
def get_polly_voice(country):
    if country == 'Italy':
       return "Giorgio"
    elif country == 'Australia':
       return "Nicole"

def set_game_flag(value, handler_input):
    if is_user_on_session(handler_input) and has_active_adventure(handler_input):
        table = boto3.resource('dynamodb').Table('AdvgGameStats')
        table.update_item(
            Key={
                'PlayerNumber': handler_input.attributes_manager.session_attributes["user"]['Items'][0]['PlayerNumber'],
                'CountryId' : get_country_id(handler_input.attributes_manager.session_attributes["country"])
            },
            UpdateExpression="set ActiveFlag=:n",
            ConditionExpression="ActiveFlag=:a",
            ExpressionAttributeValues={
                ':n': 'N',
                ':a': 'Y'
            }
        )

def start_new_adventure(handler_input):
    #create initial game stat record
    table = boto3.resource('dynamodb').Table('AdvgGameStats')
    date = str(dt.datetime.today().strftime("%Y-%m-%d"))

    #add selected country to session
    handler_input.attributes_manager.session_attributes["country"] = handler_input.request_envelope.request.intent.slots['country'].value

    new_adventure = {
        "PlayerNumber": handler_input.attributes_manager.session_attributes["user"]['Items'][0]['PlayerNumber'],
        "QuestionNumber": 0,
        "CountryId": get_country_id(handler_input.request_envelope.request.intent.slots['country'].value),
        "CurrentTurns": 0,
        "MoneyLevel": 50,
        "EnergyLevel": 50,
        "ActiveFlag" : 'Y',
        "Date": date
    }

    table.put_item(
            Item=new_adventure
        )  # dynamo is case-sensitive

    #put the stats on the session
    handler_input.attributes_manager.session_attributes["stats_record"] = {'Items':[new_adventure]}

def is_game_over(stats):
    #game is over if they run out of wealth or energy or there are no questions left
    if stats['Items'][0]['MoneyLevel'] <= 0 or stats['Items'][0]['EnergyLevel'] <=0 or stats['Items'][0]['ActiveFlag'] == 'N':
        return True
    else:
        return False

def is_warning_needed(current_wealth,current_energy):
    if current_wealth <= 10 or current_energy <= 10:
        return True
    else:
        return False

#add graphical component to the skill
def include_display(handler_input):
    #APL Directive Code
    if supports_apl(handler_input):
        handler_input.response_builder.add_directive(
            RenderDocumentDirective(
                document=load_apl_document("main.json"),
                datasources=load_apl_document("datasources.json")
            )
        )

def supports_apl(handler_input):
    # type: (HandlerInput) -> bool
    """Check if display is supported by the skill."""
    try:
        if hasattr(handler_input.request_envelope.context.system.device.supported_interfaces, 'alexa_presentation_apl'):
            if(handler_input.request_envelope.context.system.device.supported_interfaces.alexa_presentation_apl is not None):
                return True
            else:
                return False
        else:
            return False
    except:
        return False

#APL helper functions
def load_apl_document(file_path):
    # type: (str) -> Dict[str, Any]
    """Load the apl json document at the path into a dict object."""
    with open(file_path) as f:
        return json.load(f)

#Device Address API
def get_user_country(handler_input):
    base_uri = handler_input.request_envelope.context.system.api_endpoint
    device_id = handler_input.request_envelope.context.system.device.device_id
    api_access_token = handler_input.request_envelope.context.system.api_access_token
    response = requests.get(base_uri + "/v1/devices/" + device_id + "/settings/address/countryAndPostalCode", 
                    headers = {
                        'Accept': 'application/json',
                        'Authorization': 'Bearer {}'.format(api_access_token)
                    }
                )
    data = json.loads(response.text)
    
    return data["countryCode"]

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
sb.add_request_handler(YesIntentHandler())
sb.add_request_handler(NoIntentHandler())

# Add exception handler to the skill.
sb.add_exception_handler(CatchAllExceptionHandler())

# Add request and response interceptors
sb.add_global_response_interceptor(LoggingResponseInterceptor())
sb.add_global_request_interceptor(LoggingRequestInterceptor())

# Expose the lambda handler function that can be tagged to AWS Lambda handler
handler = sb.lambda_handler()