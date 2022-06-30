from datetime import datetime
from re import template
import flask_restful as restful
from sqlalchemy.exc import IntegrityError
from app.utils.auth import verify_token
from flask import g, request
from app.invitationletter.models import InvitationTemplate
from app.registration.models import Offer, Registration, RegistrationAnswer, RegistrationQuestion, Registration, RegistrationForm
from app.invitedGuest.models import InvitedGuest, GuestRegistrationAnswer, GuestRegistration
from app.invitationletter.mixins import InvitationMixin
from app.invitationletter.models import InvitationLetterRequest
from app.invitationletter.generator import generate
from app.users.models import AppUser, Country
from app import db, LOGGER
from app.utils import errors
from app.utils.auth import auth_required
from app.events.repository import EventRepository


def invitation_info(invitation_request):
    return {
        'invitation_letter_request_id': invitation_request.id,
    }


def find_registration_answer(is_guest_registration: bool, registration_question_id: int, user_id: int, event_id: int): 
    if is_guest_registration:
        answer = (
                db.session.query(GuestRegistrationAnswer)
                    .filter_by(is_active=True)
                    .join(GuestRegistration, GuestRegistrationAnswer.guest_registration_id == GuestRegistration.id)
                    .filter_by(user_id=user_id)
                    .join(RegistrationForm, GuestRegistration.registration_form_id == RegistrationForm.id)
                    .filter_by(event_id=event_id)
                    .filter(GuestRegistrationAnswer.registration_question_id == registration_question_id)
                    .first())
    else:
        answer = (
            db.session.query(RegistrationAnswer)
                .join(Registration, RegistrationAnswer.registration_id == Registration.id)
                .join(Offer, Offer.id == Registration.offer_id)
                .filter_by(user_id=user_id, event_id=event_id)
                .filter(RegistrationAnswer.registration_question_id == registration_question_id)
                .first())
    return answer


class InvitationLetterAPI(InvitationMixin, restful.Resource):

    @auth_required
    def post(self):
        # Process arguments
        args = self.req_parser.parse_args()
        event_id = args['event_id']
        work_address = args['work_address'] if args['work_address'] is not None else ' '
        addressed_to = args['addressed_to'] or 'Whom it May Concern'
        residential_address = args['residential_address']
        passport_name = args['passport_name']
        passport_no = args['passport_no']
        passport_issued_by = args['passport_issued_by']
        passport_expiry_date = datetime.strptime((args['passport_expiry_date']), '%Y-%m-%d')
        date_of_birth = datetime.strptime((args['date_of_birth']), '%Y-%m-%d')
        country_of_residence = args['country_of_residence']
        country_of_nationality = args['country_of_nationality']

        registration_event = EventRepository.get_by_id(event_id)
        if(registration_event is not None):
            to_date = registration_event.end_date
            from_date = registration_event.start_date
        else:
            return errors.EVENT_ID_NOT_FOUND

        # Finding registation_id for this user at this event
        user_id = verify_token(request.headers.get('Authorization'))['id']
        offer = db.session.query(Offer).filter(
            Offer.user_id == user_id).filter(Offer.event_id == event_id).first()
        registration_form = db.session.query(RegistrationForm).filter(
            RegistrationForm.event_id == event_id).first()

        if not registration_form:
            return errors.REGISTRATION_FORM_NOT_FOUND
            
        # Check if Guest Registration
        registration = None

        registration = db.session.query(GuestRegistration).filter(
            GuestRegistration.user_id == user_id).filter(GuestRegistration.registration_form_id == registration_form.id).first()
        if registration:
            is_guest_registration = True
            invited_guest = db.session.query(InvitedGuest).filter_by(event_id=event_id, user_id=user_id).first()
        else:
            is_guest_registration = False
            invited_guest = None

        # Normal Registration
        if (not registration) and offer:
            registration = db.session.query(Registration).filter(
                Registration.offer_id == offer.id).first()

        if not registration:
            return errors.REGISTRATION_NOT_FOUND

        try:
            if(is_guest_registration):
                invitation_letter_request = InvitationLetterRequest(
                    guest_registration_id=registration.id,
                    event_id=event_id,
                    work_address=work_address,
                    addressed_to=addressed_to,
                    residential_address=residential_address,
                    passport_name=passport_name,
                    passport_no=passport_no,
                    passport_issued_by=passport_issued_by,
                    passport_expiry_date=passport_expiry_date,
                    to_date=to_date,
                    from_date=from_date
                )
            else:
                invitation_letter_request = InvitationLetterRequest(
                    registration_id=registration.id,
                    event_id=event_id,
                    work_address=work_address,
                    addressed_to=addressed_to,
                    residential_address=residential_address,
                    passport_name=passport_name,
                    passport_no=passport_no,
                    passport_issued_by=passport_issued_by,
                    passport_expiry_date=passport_expiry_date,
                    to_date=to_date,
                    from_date=from_date
                )
            db.session.add(invitation_letter_request)
            db.session.commit()
        except Exception as e:
            LOGGER.error('Failed to add invitation letter request for user id {} due to: {}'.format(user_id, e))
            return errors.ADD_INVITATION_REQUEST_FAILED

        if (is_guest_registration and invited_guest is not None and invited_guest.role == "Indaba X"):
            LOGGER.info("Generating invitation letter for IndabaX Guest")
            accommodation = True
            travel = True
        elif is_guest_registration:
            LOGGER.info("Generating invitation letter for Invited Guest")
            accommodation = False
            travel = False
        elif offer is not None:
            accommodation = offer.accepted_accommodation_award
            travel = offer.accepted_travel_award
            LOGGER.info(f"Generating invitation letter for General attendee with accommodation: {accommodation}, Travel: {travel}")
        
        invitation_template = (
            db.session.query(InvitationTemplate)
            .filter_by(
                event_id=event_id,
                send_for_both_travel_accommodation=travel and accommodation,
                send_for_travel_award_only=travel and not accommodation,
                send_for_accommodation_award_only=accommodation and not travel)
            .first())
        
        template_url = invitation_template.template_path
        LOGGER.info(f"Using template_url: {template_url}")

        user = db.session.query(AppUser).filter(AppUser.id==user_id).first()

        # Poster registration
        bringing_poster = ""
        poster_registration_question = (db.session.query(RegistrationQuestion)
                .filter_by(
                    headline="Will you be bringing a poster?",
                    registration_form_id=registration_form.id
                ).first())
        poster_title_question = (db.session.query(RegistrationQuestion)
                .filter_by(
                    headline="What is the provisional title of your poster?",
                    registration_form_id=registration_form.id
                ).first())
        if poster_registration_question is not None:
            poster_answer = find_registration_answer(is_guest_registration, poster_registration_question.id, user_id, event_id)
            if poster_answer is not None and poster_answer.value == 'yes':
                bringing_poster = "The participant will be presenting a poster of their research"
                if poster_title_question is not None:
                    poster_title_answer = find_registration_answer(is_guest_registration, poster_title_question.id, user_id, event_id)
                    if poster_title_answer is not None and len(poster_title_answer.value) > 0:
                        bringing_poster += f' titled "{poster_title_answer.value}"'
                
                bringing_poster += "."
        
        LOGGER.info(f"Bringing poster: {bringing_poster}")
        # Handling fields
        invitation_letter_request.invitation_letter_sent_at=datetime.now()
        is_sent = generate(template_path=template_url,
                            event_id=event_id,
                            work_address=work_address,
                            addressed_to=addressed_to,
                            residential_address=residential_address,
                            passport_name=passport_name,
                            passport_no=passport_no,
                            passport_issued_by=passport_issued_by,
                            invitation_letter_sent_at=invitation_letter_request.invitation_letter_sent_at.strftime("%Y-%m-%d"),
                            expiry_date=passport_expiry_date.strftime("%Y-%m-%d"),
                            to_date=to_date.strftime("%Y-%m-%d"),
                            from_date=from_date.strftime("%Y-%m-%d"),
                            country_of_residence=country_of_residence,
                            nationality=country_of_nationality,
                            date_of_birth=date_of_birth.strftime("%Y-%m-%d"),
                            email=user.email,
                            user_title=user.user_title,
                            firstname=user.firstname,
                            lastname=user.lastname,
                            bringing_poster=bringing_poster,
                            user=user
                            )
        if not is_sent:
            return errors.SENDING_INVITATION_FAILED

        try:
            db.session.commit()
            return invitation_info(invitation_letter_request), 201

        except Exception as e:
            LOGGER.error(
                "Failed to add invitation request for user with email: {} due to {}".format(user.email, e))
            return errors.ADD_INVITATION_REQUEST_FAILED

