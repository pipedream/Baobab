from flask import g
import flask_restful as restful
from flask_restful import reqparse, fields, marshal_with
from sqlalchemy.sql import func
from sqlalchemy import and_, or_

from app import db, LOGGER
from app.applicationModel.models import ApplicationForm
from app.events.models import EventRole
from app.responses.models import Response, ResponseReviewer
from app.reviews.mixins import ReviewMixin, GetReviewResponseMixin, PostReviewResponseMixin, PostReviewAssignmentMixin
from app.reviews.models import ReviewForm, ReviewResponse, ReviewScore
from app.users.models import AppUser
from app.utils.auth import auth_required
from app.utils.errors import EVENT_NOT_FOUND, REVIEW_RESPONSE_NOT_FOUND, FORBIDDEN, USER_NOT_FOUND

option_fields = {
    'value': fields.String,
    'label': fields.String
}

review_question_fields = {
    'id': fields.Integer,
    'question_id': fields.Integer,
    'description': fields.String,
    'headline': fields.String,
    'type': fields.String,
    'placeholder': fields.String,
    'options': fields.List(fields.Nested(option_fields)),
    'is_required': fields.Boolean,
    'order': fields.Integer,
    'validation_regex': fields.String,
    'validation_text': fields.String,
    'weight': fields.Float
}

review_form_fields = {
    'id': fields.Integer,
    'application_form_id': fields.Integer,
    'is_open': fields.Boolean,
    'deadline': fields.DateTime('iso8601'),
    'review_questions': fields.List(fields.Nested(review_question_fields))
}

answer_fields = {
    'id': fields.Integer,
    'question_id': fields.Integer,
    'question': fields.String(attribute='question.headline'),
    'value': fields.String(attribute='value_display')
}

response_fields = {
    'id': fields.Integer,
    'application_form_id': fields.Integer,
    'user_id': fields.Integer,
    'is_submitted': fields.Boolean,
    'submitted_timestamp': fields.DateTime(dt_format='iso8601'),
    'is_withdrawn': fields.Boolean,
    'withdrawn_timestamp': fields.DateTime(dt_format='iso8601'),
    'started_timestamp': fields.DateTime(dt_format='iso8601'),
    'answers': fields.List(fields.Nested(answer_fields))
}

user_fields = {
    'nationality_country': fields.String(attribute='nationality_country.name'),
    'residence_country': fields.String(attribute='residence_country.name'),
    'affiliation': fields.String,
    'department': fields.String,
    'user_category': fields.String(attribute='user_category.name')
}

review_response_fields = {
    'review_form': fields.Nested(review_form_fields),
    'response': fields.Nested(response_fields),
    'user': fields.Nested(user_fields),
    'reviews_remaining_count': fields.Integer
}

class ReviewResponseUser():
    def __init__(self, review_form, response, reviews_remaining_count):
        self.review_form = review_form
        self.response = response
        self.user = None if response is None else response.user
        self.reviews_remaining_count = reviews_remaining_count

class ReviewAPI(ReviewMixin, restful.Resource):

    @auth_required
    @marshal_with(review_response_fields)
    def get(self):
        args = self.req_parser.parse_args()
        event_id = args['event_id']
        
        review_form = db.session.query(ReviewForm)\
                        .join(ApplicationForm, ApplicationForm.id==ReviewForm.application_form_id)\
                        .filter_by(event_id=event_id)\
                        .first()
        if review_form is None:
            return EVENT_NOT_FOUND

        reviews_remaining_count = db.session.query(func.count(ResponseReviewer.id))\
                        .filter_by(reviewer_user_id=g.current_user['id'])\
                        .join(Response)\
                        .filter_by(is_withdrawn=False, application_form_id=review_form.application_form_id, is_submitted=True)\
                        .outerjoin(ReviewResponse, and_(ReviewResponse.response_id==ResponseReviewer.response_id, ReviewResponse.reviewer_user_id==g.current_user['id']))\
                        .filter_by(id=None)\
                        .all()[0][0]

        skip = self.sanitise_skip(args['skip'], reviews_remaining_count)

        response = db.session.query(Response)\
                        .filter_by(is_withdrawn=False, application_form_id=review_form.application_form_id, is_submitted=True)\
                        .join(ResponseReviewer)\
                        .filter_by(reviewer_user_id=g.current_user['id'])\
                        .outerjoin(ReviewResponse, and_(ReviewResponse.response_id==ResponseReviewer.response_id, ReviewResponse.reviewer_user_id==g.current_user['id']))\
                        .filter_by(id=None)\
                        .order_by(ResponseReviewer.response_id)\
                        .offset(skip)\
                        .first()
        
        return ReviewResponseUser(review_form, response, reviews_remaining_count)

    def sanitise_skip(self, skip, reviews_remaining_count):
        if skip is None:
            skip = 0

        if skip < 0:
            skip = 0

        if reviews_remaining_count == 0:
            skip = 0
        elif skip >= reviews_remaining_count:
            skip = reviews_remaining_count - 1
        
        return skip


review_scores_fields = {
    'review_question_id': fields.Integer,
    'value': fields.String
}

review_response_fields = {
    'id': fields.Integer,
    'review_form_id': fields.Integer,
    'response_id': fields.Integer,
    'reviewer_user_id': fields.Integer,
    'scores': fields.List(fields.Nested(review_scores_fields), attribute='review_scores')
}

class ReviewResponseAPI(GetReviewResponseMixin, PostReviewResponseMixin, restful.Resource):

    @auth_required
    @marshal_with(review_response_fields)
    def get(self):
        args = self.get_req_parser.parse_args()
        review_form_id = args['review_form_id']
        response_id = args['response_id']
        reviewer_user_id = g.current_user['id']

        review_response = db.session.query(ReviewResponse)\
                            .filter_by(review_form_id=review_form_id, response_id=response_id, reviewer_user_id=reviewer_user_id)\
                            .first()
        if review_response is None:
            return REVIEW_RESPONSE_NOT_FOUND

        return review_response

    @auth_required
    def post(self):
        args = self.post_req_parser.parse_args()
        validation_result = self.validate_scores(args['scores'])
        if validation_result is not None:
            return validation_result

        response_id = args['response_id']
        review_form_id = args['review_form_id']
        reviewer_user_id = g.current_user['id']
        scores = args['scores']

        response_reviewer = self.get_response_reviewer(response_id, reviewer_user_id)
        if response_reviewer is None:
            return FORBIDDEN

        review_response = ReviewResponse(review_form_id, reviewer_user_id, response_id)
        review_response.review_scores = self.get_review_scores(scores)
        db.session.add(review_response)
        db.session.commit()

        return {}, 201

    @auth_required
    def put(self):
        args = self.post_req_parser.parse_args()
        validation_result = self.validate_scores(args['scores'])
        if validation_result is not None:
            return validation_result
        
        response_id = args['response_id']
        review_form_id = args['review_form_id']
        reviewer_user_id = g.current_user['id']
        scores = args['scores']

        response_reviewer = self.get_response_reviewer(response_id, reviewer_user_id)
        if response_reviewer is None:
            return FORBIDDEN

        review_response = self.get_review_response(review_form_id, response_id, reviewer_user_id)
        if review_response is None:
            return REVIEW_RESPONSE_NOT_FOUND
        
        db.session.query(ReviewScore).filter(ReviewScore.review_response_id==review_response.id).delete()
        review_response.review_scores = self.get_review_scores(scores)
        db.session.commit()

        return {}, 200
    
    def get_response_reviewer(self, response_id, reviewer_user_id):
        return db.session.query(ResponseReviewer)\
                         .filter_by(response_id=response_id, reviewer_user_id=reviewer_user_id)\
                         .first()

    def get_review_response(self, review_form_id, response_id, reviewer_user_id):
        return db.session.query(ReviewResponse)\
                         .filter_by(review_form_id=review_form_id, response_id=response_id, reviewer_user_id=reviewer_user_id)\
                         .first()
    
    def get_review_scores(self, scores):
        review_scores = []
        for score in scores:
            review_score = ReviewScore(score['review_question_id'], score['value'])
            review_scores.append(review_score)
        return review_scores
    
    def validate_scores(self, scores):
        for score in scores:
            if 'review_question_id' not in score.keys():
                return self.get_error_message('review_question_id')
            if 'value' not in score.keys():
                return self.get_error_message('value')
    
    def get_error_message(self, key):
        return ({'message': {key: 'Missing required parameter in the JSON body or the post body or the query string'}}, 400)

class ReviewAssignmentAPI(PostReviewAssignmentMixin, restful.Resource):
    
    @auth_required
    def post(self):
        args = self.post_req_parser.parse_args()
        user_id = g.current_user['id']
        event_id = args['event_id']
        reviewer_user_email = args['reviewer_user_email']
        num_reviews = args['num_reviews']

        is_user_admin = db.session.query(AppUser).get(user_id).is_admin
        current_user_roles = self.get_roles(user_id, event_id)
        if 'admin' not in current_user_roles and not is_user_admin:
            return FORBIDDEN
        
        reviewer_user = self.get_reviewer_user(reviewer_user_email)
        if reviewer_user is None:
            return USER_NOT_FOUND
        
        reviewer_roles = self.get_roles(reviewer_user.id, event_id)
        if reviewer_roles is None or 'reviewer' not in reviewer_roles:
            self.add_reviewer_role(reviewer_user.id, event_id)

        response_ids = self.get_eligible_response_ids(reviewer_user.id, num_reviews)
        response_reviewers = [ResponseReviewer(response_id, reviewer_user.id) for response_id in response_ids]
        db.session.add_all(response_reviewers)
        db.session.commit()
        
        return {}, 201


    def get_roles(self, user_id, event_id):
        return list(map(lambda event_role: event_role[0], db.session.query(EventRole.role).filter_by(event_id=event_id, user_id=user_id).all()))

    def get_reviewer_user(self, reviewer_user_email):
        return db.session.query(AppUser).filter_by(email=reviewer_user_email).first()
    
    def add_reviewer_role(self, user_id, event_id):
        event_role = EventRole('reviewer', user_id, event_id)
        db.session.add(event_role)
        db.session.commit()
    
    def get_eligible_response_ids(self, reviewer_user_id, num_reviews):
        responses = db.session.query(Response.id)\
                         .filter(Response.user_id != reviewer_user_id, Response.is_submitted==True, Response.is_withdrawn==False)\
                         .outerjoin(ResponseReviewer, Response.id==ResponseReviewer.response_id)\
                         .filter(or_(ResponseReviewer.reviewer_user_id != reviewer_user_id, ResponseReviewer.id == None))\
                         .group_by(Response.id)\
                         .having(func.count(ResponseReviewer.reviewer_user_id) < 3)\
                         .limit(num_reviews)\
                         .all()
        
        return list(map(lambda response: response[0], responses))