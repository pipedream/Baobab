from app.registration.models import RegistrationForm
from app.registration.models import RegistrationQuestion
from app.registration.models import RegistrationSection
import json
from datetime import datetime, timedelta
from app import db, LOGGER
from app.utils.testing import ApiTestCase
from app.users.models import AppUser, UserCategory, Country
from app.events.models import Event
from app.registration.models import Offer, OfferTag
from app.organisation.models import Organisation
from app.outcome.repository import OutcomeRepository as outcome_repository
from app.outcome.models import Status
from app.responses.models import Response


OFFER_DATA = {
    'id': 1,
    'user_id': 1,
    'event_id': 1,
    'offer_date': datetime(1984, 12, 12).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
    'expiry_date': datetime(1984, 12, 12).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
    'payment_required': False,
    'travel_award': False,
    'accommodation_award': False,
    'accepted_accommodation_award': None,
    'accepted_travel_award': None,
    'rejected_reason': 'N/A',
}

REGISTRATION_FORM = {
    'event_id': 1,
}

REGISTRATION_SECTION = {
    'registration_form_id': 1,
    'name': "section 2",
    'description': "this is the second section",
    'order': 1,
    'show_for_accommodation_award': True,
    'show_for_travel_award': True,
    'show_for_payment_required': True
}

REGISTRATION_QUESTION = {
    'registration_form_id': 1,
    'section_id': 1,
    'type': "open-ended",
    'description': "just a question",
    'headline': "question headline",
    'placeholder': "answer the this question",
    'validation_regex': "/[a-d]",
    'validation_text': "regex are cool",
    'order': 1,
    'options': "{'a': 'both a and b', 'b': 'none of the above'}",
    'is_required': True
}


class OfferApiTest(ApiTestCase):

    def _seed_static_data(self, add_offer=True):
        test_user = self.add_user('something@email.com')
        offer_admin = self.add_user('offer_admin@ea.com', 'event_admin', is_admin=True)
        self.add_organisation('Deep Learning Indaba', 'blah.png', 'blah_big.png', 'deeplearningindaba')
        db.session.add(UserCategory('Offer Category'))
        db.session.add(Country('Suid Afrika'))
        db.session.commit()

        event = self.add_event(
            name={'en': "Tech Talk"},
            description={'en': "tech talking"},
            start_date=datetime(2019, 12, 12),
            end_date=datetime(2020, 12, 12),
            key='SPEEDNET'
        )
        db.session.commit()

        app_form = self.create_application_form()
        self.add_response(app_form.id, test_user.id, True, False)

        if add_offer:
            offer = Offer(
                user_id=test_user.id,
                event_id=event.id,
                offer_date=datetime.now(),
                expiry_date=datetime.now() + timedelta(days=15),
                payment_required=False,
                travel_award=True,
                accommodation_award=False)
            db.session.add(offer)
            db.session.commit()

        self.headers = self.get_auth_header_for("something@email.com")
        self.adminHeaders = self.get_auth_header_for("offer_admin@ea.com")

        self.add_email_template('offer')

        db.session.flush()

    def get_auth_header_for(self, email):
        body = {
            'email': email,
            'password': 'abc'
        }
        response = self.app.post('api/v1/authenticate', data=body)
        data = json.loads(response.data)
        header = {'Authorization': data['token']}
        return header

    def test_create_offer(self):
        self._seed_static_data(add_offer=False)

        response = self.app.post(
            '/api/v1/offer',
            data=json.dumps(OFFER_DATA),
            headers=self.adminHeaders,
            content_type='application/json'
        )
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 201)
        self.assertFalse(data['payment_required'])
        self.assertFalse(data['travel_award'])
        self.assertFalse(data['accommodation_award'])

        outcome = outcome_repository.get_latest_by_user_for_event(OFFER_DATA['user_id'], OFFER_DATA['event_id'])
        self.assertEqual(outcome.status, Status.ACCEPTED)

    def test_create_offer_with_template(self):
        self._seed_static_data(add_offer=False)
        
        offer_data = OFFER_DATA.copy()
        offer_data['email_template'] = """Dear {user_title} {first_name} {last_name},

        This is a custom email notifying you about your place at the {event_name}.

        Visit {host}/offer to accept it, you have until {expiry_date} to do so!

        kthanksbye!    
        """

        response = self.app.post(
            '/api/v1/offer',
            data=json.dumps(offer_data),
            headers=self.adminHeaders,
            content_type='application/json'
        )
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 201)
        self.assertFalse(data['payment_required'])
        self.assertFalse(data['travel_award'])
        self.assertFalse(data['accommodation_award'])

    def test_create_duplicate_offer(self):
        self._seed_static_data(add_offer=True)

        response = self.app.post('/api/v1/offer', data=OFFER_DATA,
                                 headers=self.adminHeaders)
        data = json.loads(response.data)

        self.assertEqual(response.status_code, 409)

    def test_get_offer(self):
        self._seed_static_data(add_offer=True)

        event_id = 1
        url = "/api/v1/offer?event_id=%d" % (
            event_id)

        response = self.app.get(url, headers=self.headers)

        self.assertEqual(response.status_code, 200)

    def test_get_offer_not_found(self):
        self._seed_static_data()

        event_id = 12
        url = "/api/v1/offer?event_id=%d" % (
            event_id)

        response = self.app.get(url, headers=self.headers)

        self.assertEqual(response.status_code, 404)

    def test_update_offer(self):
        self._seed_static_data()
        event_id = 1
        offer_id = 1
        candidate_response = True
        rejected_reason = "the reason for rejection"
        url = "/api/v1/offer?offer_id=%d&event_id=%d&candidate_response=%s&rejected_reason=%s" % (
            offer_id, event_id, candidate_response, rejected_reason)

        response = self.app.put(url, headers=self.headers)

        data = json.loads(response.data)
        LOGGER.debug("Offer-PUT: {}".format(response.data))

        self.assertEqual(response.status_code, 201)
        self.assertTrue(data['candidate_response'])

class OfferTagAPITest(ApiTestCase):

    def _seed_static_data(self):

        self.event = self.add_event(key='event1')
        db.session.commit()

        test_user = self.add_user('test_user@mail.com')
        offer_admin = self.add_user('offeradmin@mail.com')
        db.session.commit()
        self.test_user_id = test_user.id

        self.event.add_event_role('admin', offer_admin.id)
        db.session.commit()

        app_form = self.create_application_form()
        self.add_response(app_form.id, self.test_user_id, True, False)

        self.offer = self.add_offer(self.test_user_id, self.event.id)

        self.tag1 = self.add_tag(tag_type='REGISTRATION')
        self.tag2 = self.add_tag(names={'en': 'Tag 2 en', 'fr': 'Tag 2 fr'}, descriptions={'en': 'Tag 2 en description', 'fr': 'Tag 2 fr description'}, tag_type='REGISTRATION')
        self.tag_offer(self.offer.id, self.tag1.id)

        db.session.flush()
    
    def get_auth_header_for(self, email):
        body = {
            'email': email,
            'password': 'abc'
        }
        response = self.app.post('api/v1/authenticate', data=body)
        data = json.loads(response.data)
        header = {'Authorization': data['token']}
        return header

    def test_tag_admin(self):
        """Test that an event admin can add a tag to an offer."""
        self._seed_static_data()

        params = {
            'event_id': self.event.id,
            'tag_id': self.tag2.id,
            'offer_id': self.offer.id
        }

        response = self.app.post(
            '/api/v1/offertag',
            headers=self.get_auth_header_for('offeradmin@mail.com'),
            json=params)

        self.assertEqual(response.status_code, 201)

        params = {
            'event_id': self.event.id,
            'user_id' : self.test_user_id,
            'language': 'en',
        }

        response = self.app.get(
            '/api/v1/offer',
            headers=self.get_auth_header_for('offeradmin@mail.com'),
            json=params)

        data = json.loads(response.data)
        print(data)

        self.assertEqual(len(data[0]['tags']), 2)
        self.assertEqual(data[0]['tags'][0]['id'], 1)

    def test_remove_tag_admin(self):
        """Test that an event admin can remove a tag from an offer."""
        self._seed_static_data()

        params = {
            'event_id': self.event.id,
            'tag_id': self.tag1.id,
            'offer_id': self.offer.id
        }

        response = self.app.delete(
            '/api/v1/offertag',
            headers=self.get_auth_header_for('offeradmin@mail.com'),
            json=params)

        self.assertEqual(response.status_code, 200)

        params = {
            'event_id': self.event.id,
            'user_id' : self.test_user_id,
            'language': 'en',
        }

        response = self.app.get(
            '/api/v1/offer',
            headers=self.get_auth_header_for('offeradmin@mail.com'),
            json=params)

        data = json.loads(response.data)
        print(data)

        self.assertEqual(len(data[0]['tags']), 1)

    def test_tag_non_admin(self):
        """Test that a non admin can't add a tag to an offer."""
        self._seed_static_data()

        params = {
            'event_id': self.event.id,
            'tag_id': self.tag1.id,
            'offer_id': self.offer.id
        }

        response = self.app.post(
            '/api/v1/offertag',
            headers=self.get_auth_header_for('test_user@mail.com'),
            json=params)

        self.assertEqual(response.status_code, 403)

    def test_remove_tag_non_admin(self):
        """Test that a non admin can't remove a tag from an offer."""
        self._seed_static_data()

        params = {
            'event_id': self.event.id,
            'tag_id': self.tag1.id,
            'offer_id': self.offer.id
        }

        response = self.app.delete(
            '/api/v1/offertag',
            headers=self.get_auth_header_for('test_user@mail.com'),
            json=params)

        self.assertEqual(response.status_code, 403)

class RegistrationTest(ApiTestCase):

    def _seed_static_data(self):
        test_user = self.add_user('something@email.com', 'Some', 'Thing', 'Mr')
        event_admin = self.add_user('event_admin@ea.com', 'event_admin', is_admin=True)
        self.add_organisation('Deep Learning Indaba', 'blah.png', 'blah_big.png')
        db.session.add(UserCategory('Postdoc'))
        db.session.add(Country('South Africa'))
        db.session.commit()

        event = self.add_event(
            name={'en': "Tech Talk"},
            description={'en': "tech talking"},
            start_date=datetime(2019, 12, 12, 10, 10, 10),
            end_date=datetime(2020, 12, 12, 10, 10, 10),
            key='SPEEDNET'
        )
        db.session.commit()

        self.event_id = event.id

        offer = Offer(
            user_id=test_user.id,
            event_id=event.id,
            offer_date=datetime.now(),
            expiry_date=datetime.now() + timedelta(days=15),
            payment_required=False,
            travel_award=True,
            accommodation_award=False)

        offer.candidate_response = True
        offer.accepted_travel_award = True
        offer.accepted_accommodation_award = True

        db.session.add(offer)
        db.session.commit()
        self.offer_id = offer.id

        form = RegistrationForm(
            event_id=event.id
        )
        db.session.add(form)
        db.session.commit()

        section = RegistrationSection(
            registration_form_id=form.id,
            name="Section 1",
            description="the section description",
            order=1,
            show_for_travel_award=True,
            show_for_accommodation_award=True,
            show_for_payment_required=False,
        )
        db.session.add(section)
        db.session.commit()

        section2 = RegistrationSection(
            registration_form_id=form.id,
            name="Section 2",
            description="the section 2 description",
            order=1,
            show_for_travel_award=True,
            show_for_accommodation_award=True,
            show_for_payment_required=False,
        )
        db.session.add(section2)
        db.session.commit()

        question = RegistrationQuestion(
            section_id=section.id,
            registration_form_id=form.id,
            description="Question 1",
            type="short-text",
            is_required=True,
            order=1,
            placeholder="the placeholder",
            headline="the headline",
            validation_regex="[]/",
            validation_text=" text"
        )
        db.session.add(question)
        db.session.commit()

        question2 = RegistrationQuestion(
            section_id=section2.id,
            registration_form_id=form.id,
            description="Question 2",
            type="short-text",
            is_required=True,
            order=1,
            placeholder="the placeholder",
            headline="the headline",
            validation_regex="[]/",
            validation_text=" text"
        )
        db.session.add(question2)
        db.session.commit()

        self.headers = self.get_auth_header_for("something@email.com")
        self.adminHeaders = self.get_auth_header_for("event_admin@ea.com")

        db.session.flush()

    def test_create_registration_form(self):
        self._seed_static_data()
        response = self.app.post(
            '/api/v1/registration-form', data=REGISTRATION_FORM, headers=self.adminHeaders)
        data = json.loads(response.data)
        LOGGER.debug(
            "Reg-form: {}".format(data))
        assert response.status_code == 201
        assert data['registration_form_id'] == 2

    def test_get_form(self):
        self._seed_static_data()

        params = {'offer_id': self.offer_id, 'event_id': self.event_id}
        response = self.app.get("/api/v1/registration-form", headers=self.headers, data=params)

        form = json.loads(response.data)
        self.assertEqual(response.status_code, 201)
        assert form['registration_sections'][0]['registration_questions'][0]['type'] == 'short-text'
        assert form['registration_sections'][0]['name'] == 'Section 1'
