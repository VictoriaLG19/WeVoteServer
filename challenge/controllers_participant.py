# challenge/controllers_participant.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from datetime import datetime
from django.contrib import messages
from django.db.models import F, Q

from .models import Challenge, ChallengeInvitee, ChallengeManager, ChallengeParticipant
from position.models import OPPOSE, SUPPORT
from share.models import SharedLinkClicked
from voter.models import Voter, VoterManager
import wevote_functions.admin
from wevote_functions.functions import generate_dict_from_list_with_key_from_one_attribute, positive_value_exists
from wevote_functions.functions_date import generate_date_as_integer, get_current_date_as_integer, DATE_FORMAT_YMD_HMS

logger = wevote_functions.admin.get_logger(__name__)


def challenge_participant_retrieve_for_api(  # challengeParticipantRetrieve
        voter_device_id='',
        challenge_we_vote_id=''):
    status = ''

    dict_results = generate_challenge_participant_dict_from_challenge_participant_object()
    error_results = dict_results['challenge_participant_dict']

    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id, read_only=True)
    if voter_results['voter_found']:
        voter = voter_results['voter']
        voter_we_vote_id = voter.we_vote_id
    else:
        status += "VALID_VOTER_ID_MISSING "
        error_results['status'] = status
        error_results['success'] = False
        return error_results

    challenge_manager = ChallengeManager()
    results = challenge_manager.retrieve_challenge_participant(
        challenge_we_vote_id=challenge_we_vote_id,
        voter_we_vote_id=voter_we_vote_id,
        read_only=True,
    )
    status += results['status']
    if not results['success']:
        status += "CHALLENGE_PARTICIPANT_RETRIEVE_ERROR "
        error_results['status'] = status
        error_results['success'] = False
        return error_results
    elif not results['challenge_participant_found']:
        status += "CHALLENGE_PARTICIPANT_NOT_FOUND: "
        status += results['status'] + " "
        error_results['status'] = status
        error_results['success'] = True
        return error_results

    challenge_participant = results['challenge_participant']
    dict_results = generate_challenge_participant_dict_from_challenge_participant_object(
        challenge_participant=challenge_participant)
    status += dict_results['status']
    if dict_results['success']:
        results = dict_results['challenge_participant_dict']
        results['status'] = status
        results['success'] = True
        return results
    else:
        status += "CHALLENGE_PARTICIPANT_GENERATE_RESULTS_ERROR "
        error_results['status'] = status
        return error_results


def challenge_participant_list_retrieve_for_api(  # challengeParticipantListRetrieve
        voter_device_id='',
        challenge_we_vote_id=''):
    status = ''

    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id, read_only=True)
    if voter_results['voter_found']:
        voter = voter_results['voter']
        voter_we_vote_id = voter.we_vote_id
    else:
        status += "VALID_VOTER_ID_MISSING "
        results = {
            'status':                       status,
            'success':                      False,
            'challenge_participant_list':   [],
            'challenge_we_vote_id':         challenge_we_vote_id,
            'voter_we_vote_id':             '',
        }
        return results

    challenge_manager = ChallengeManager()
    results = challenge_manager.retrieve_challenge_participant_list(
        challenge_we_vote_id=challenge_we_vote_id,
        read_only=True,
    )
    status += results['status']
    if not results['success']:
        status += "CHALLENGE_PARTICIPANT_LIST_RETRIEVE_ERROR "
        results = {
            'status':                       status,
            'success':                      False,
            'challenge_participant_list':   [],
            'challenge_we_vote_id':         challenge_we_vote_id,
            'voter_we_vote_id':             '',
        }
        return results
    elif not results['participant_list_found']:
        status += "CHALLENGE_PARTICIPANT_LIST_NOT_FOUND: "
        status += results['status'] + " "

    challenge_participant_list = []
    for challenge_participant in results['participant_list']:
        generate_results = generate_challenge_participant_dict_from_challenge_participant_object(
            challenge_participant=challenge_participant)
        if generate_results['success']:
            challenge_participant_list.append(generate_results['challenge_participant_dict'])
    results = {
        'status':                       status,
        'success':                      True,
        'challenge_participant_list':   challenge_participant_list,
        'challenge_we_vote_id':         challenge_we_vote_id,
        'voter_we_vote_id':             voter_we_vote_id,
    }
    return results


def challenge_participant_save_for_api(  # challengeParticipantSave
        challenge_we_vote_id='',
        invite_text_for_friends='',
        invite_text_for_friends_changed=False,
        visible_to_public=False,
        visible_to_public_changed=False,
        voter_device_id=''):
    challenge_invitee = None
    inviter_voter_we_vote_id = ''
    participant_name_changed = False
    status = ''
    success = True

    generate_results = generate_challenge_participant_dict_from_challenge_participant_object()
    error_results = generate_results['challenge_participant_dict']

    voter_manager = VoterManager()
    voter_results = voter_manager.retrieve_voter_from_voter_device_id(voter_device_id, read_only=True)
    if voter_results['voter_found']:
        voter = voter_results['voter']
        participant_name = voter.get_full_name(True)
        if positive_value_exists(participant_name):
            participant_name_changed = True
        voter_we_vote_id = voter.we_vote_id
        linked_organization_we_vote_id = voter.linked_organization_we_vote_id
    else:
        status += "VALID_VOTER_ID_MISSING "
        results = error_results
        results['status'] = status
        return results
    # To participate in a challenge, voter must be signed in
    if not voter.is_signed_in():
        status += "PARTICIPANT_NOT_SIGNED_IN "
        results = error_results
        results['status'] = status
        return results

    if not positive_value_exists(challenge_we_vote_id):
        status += "CHALLENGE_WE_VOTE_ID_REQUIRED "
        results = error_results
        results['status'] = status
        return results

    # Before calling update_or_create_challenge_participant, see if voter was invited by a current participant,
    #  so we can give points credit for this new participant.
    shared_item_code_list = []
    # Search SharedLinkClicked for viewed_by_voter_we_vote_id for this challenge, to get shared_item_code list,
    #  that led to this voter viewing this challenge.
    #  This is the proof that this voter was invited by a current participant.
    try:
        queryset = SharedLinkClicked.objects.using('readonly').filter(viewed_by_voter_we_vote_id=voter_we_vote_id)
        link_clicked_list = list(queryset)
        shared_item_code_list = []
        for link_clicked in link_clicked_list:
            if positive_value_exists(link_clicked.shared_item_code) and \
                    link_clicked.shared_item_code not in shared_item_code_list:
                shared_item_code_list.append(link_clicked.shared_item_code)
    except Exception as e:
        status += "SHARED_LINK_CLICKED_RETRIEVE_ERROR: " + str(e) + " "

    # Then find ChallengeInvitee.invitee_url_code matching shared_item_code, so we can inviter_voter_we_vote_id.
    if len(shared_item_code_list) > 0:
        try:
            queryset = ChallengeInvitee.objects.filter(
                challenge_we_vote_id=challenge_we_vote_id,
                invitee_url_code__in=shared_item_code_list)
            challenge_invitee_list = list(queryset)
            #  If found, get inviter_voter_we_vote_id from ChallengeInvitee to add to ChallengeParticipant.
            if len(challenge_invitee_list) > 0:
                challenge_invitee = challenge_invitee_list[0]
                inviter_voter_we_vote_id = challenge_invitee.inviter_voter_we_vote_id
        except Exception as e:
            status += "CHALLENGE_INVITEE_RETRIEVE_ERROR: " + str(e) + " "

    if hasattr(challenge_invitee, 'invitee_voter_we_vote_id'):
        # Does ChallengeInvitee already have a invitee_voter_we_vote_id? (from viewed_by_voter_we_vote_id)
        if positive_value_exists(challenge_invitee.invitee_voter_we_vote_id):
            # If so, create new ChallengeInvitee for that Participant.
            #  Add parent_invitee_id field to tie new Invitee back to parent Invitee.
            try:
                create_values = {
                    'challenge_joined': True,
                    'challenge_we_vote_id': challenge_we_vote_id,
                    'date_challenge_joined': datetime.now(),
                    'date_invite_sent': challenge_invitee.date_invite_sent,
                    'date_invite_viewed': challenge_invitee.date_invite_viewed,
                    'invite_sent': challenge_invitee.invite_sent,
                    'invite_text_from_inviter': challenge_invitee.invite_text_from_inviter,
                    'invite_viewed': challenge_invitee.invite_viewed,
                    'invite_viewed_count': 1,
                    'invitee_name': challenge_invitee.invitee_name,
                    'invitee_voter_name': participant_name,
                    'invitee_voter_we_vote_id': voter_we_vote_id,
                    'inviter_name': challenge_invitee.inviter_name,
                    'inviter_voter_we_vote_id': inviter_voter_we_vote_id,
                    'parent_invitee_id': challenge_invitee.id,
                    'we_vote_hosted_profile_image_url_medium': voter.we_vote_hosted_profile_image_url_medium,
                    'we_vote_hosted_profile_image_url_tiny': voter.we_vote_hosted_profile_image_url_tiny,
                }
                new_challenge_invitee = ChallengeInvitee.objects.create(**create_values)
            except Exception as e:
                status += "CHALLENGE_INVITEE_CREATE_ERROR: " + str(e) + " "
        else:
            # If not, update ChallengeInvitee invitee_voter_name & invitee_voter_we_vote_id with this voter_we_vote_id
            try:
                challenge_invitee.challenge_joined = True
                challenge_invitee.date_challenge_joined = datetime.now()
                challenge_invitee.invitee_voter_name = participant_name
                challenge_invitee.invitee_voter_we_vote_id = voter_we_vote_id
                challenge_invitee.we_vote_hosted_profile_image_url_medium = \
                    voter.we_vote_hosted_profile_image_url_medium
                challenge_invitee.we_vote_hosted_profile_image_url_tiny = \
                    voter.we_vote_hosted_profile_image_url_tiny
                challenge_invitee.save()
            except Exception as e:
                status += "CHALLENGE_INVITEE_UPDATE_ERROR: " + str(e) + " "

    challenge_manager = ChallengeManager()
    update_values = {
        'invite_text_for_friends':          invite_text_for_friends,
        'invite_text_for_friends_changed':  invite_text_for_friends_changed,
        'participant_name':                 participant_name,
        'participant_name_changed':         participant_name_changed,
        'visible_to_public':                visible_to_public,
        'visible_to_public_changed':        visible_to_public_changed,
    }
    if positive_value_exists(inviter_voter_we_vote_id):
        # Add inviter_voter_we_vote_id field to tie Participant back to parent Participant (who invited this voter)
        update_values['inviter_voter_we_vote_id'] = inviter_voter_we_vote_id
        update_values['inviter_voter_we_vote_id_changed'] = True
    create_results = challenge_manager.update_or_create_challenge_participant(
        challenge_we_vote_id=challenge_we_vote_id,
        voter=voter,
        voter_we_vote_id=voter_we_vote_id,
        organization_we_vote_id=linked_organization_we_vote_id,
        update_values=update_values,
    )

    status += create_results['status']
    if create_results['challenge_participant_found']:
        challenge_participant = create_results['challenge_participant']
        count_results = challenge_manager.update_challenge_participants_count(challenge_we_vote_id)

        from challenge.controllers_scoring import refresh_participant_points_for_challenge
        results = refresh_participant_points_for_challenge(
            challenge_participant_list=[challenge_participant],
            challenge_we_vote_id=challenge_we_vote_id)
        status += results['status']
        if results['success']:
            try:
                challenge_participant = ChallengeParticipant.objects.get(id=challenge_participant.id)
            except Exception as e:
                pass

        generate_results = generate_challenge_participant_dict_from_challenge_participant_object(challenge_participant)
        challenge_participant_results = generate_results['challenge_participant_dict']
        status += generate_results['status']
        challenge_participant_results['status'] = status
        challenge_participant_results['success'] = generate_results['success']
        return challenge_participant_results
    else:
        status += "CHALLENGE_PARTICIPANT_SAVE_ERROR "
        results = error_results
        results['status'] = status
        results['success'] = False
        return results


def move_participant_entries_to_another_voter(from_voter_we_vote_id, to_voter_we_vote_id, to_organization_we_vote_id):
    status = ''
    success = True
    participant_entries_moved = 0
    participant_entries_not_moved = 0
    error_results = {
        'status': status,
        'success': success,
        'from_voter_we_vote_id': from_voter_we_vote_id,
        'to_voter_we_vote_id': to_voter_we_vote_id,
        'participant_entries_moved': participant_entries_moved,
        'participant_entries_not_moved': participant_entries_not_moved,
    }

    if not positive_value_exists(from_voter_we_vote_id) or not positive_value_exists(to_voter_we_vote_id):
        status += "MOVE_PARTICIPANT_ENTRIES_TO_ANOTHER_VOTER-" \
                  "Missing either from_voter_we_vote_id or to_voter_we_vote_id "
        error_results['status'] = status
        return error_results

    if from_voter_we_vote_id == to_voter_we_vote_id:
        status += "MOVE_PARTICIPANT_ENTRIES_TO_ANOTHER_VOTER-from_voter_we_vote_id and to_voter_we_vote_id identical "
        error_results['status'] = status
        return error_results

    challenge_manager = ChallengeManager()
    results = challenge_manager.retrieve_challenge_participant_list(
        voter_we_vote_id=from_voter_we_vote_id,
        limit=0,
        require_invite_text_for_friends=False,
        require_visible_to_public=False,
        require_not_blocked_by_we_vote=False,
        read_only=False)
    from_participant_list = results['participant_list']
    results = challenge_manager.retrieve_challenge_participant_list(
        voter_we_vote_id=to_voter_we_vote_id,
        limit=0,
        require_invite_text_for_friends=False,
        require_visible_to_public=False,
        require_not_blocked_by_we_vote=False,
        read_only=False)
    to_participant_list = results['participant_list']
    to_participant_we_vote_id_list = []
    for to_participant in to_participant_list:
        if to_participant.voter_we_vote_id not in to_participant_we_vote_id_list:
            to_participant_we_vote_id_list.append(to_participant.voter_we_vote_id)

    bulk_update_list = []
    for from_participant_entry in from_participant_list:
        # See if the "to_voter" already has an entry for this issue
        if from_participant_entry.voter_we_vote_id in to_participant_we_vote_id_list:
            # Do not move this entry, since we already have an entry for this voter_we_vote_id the to_voter's list
            pass
        else:
            # Change the from_voter_we_vote_id to to_voter_we_vote_id
            try:
                from_participant_entry.voter_we_vote_id = to_voter_we_vote_id
                if positive_value_exists(to_organization_we_vote_id):
                    from_participant_entry.organization_we_vote_id = to_organization_we_vote_id
                bulk_update_list.append(from_participant_entry)
                participant_entries_moved += 1
            except Exception as e:
                participant_entries_not_moved += 1
                status += "FAILED_FROM_PARTICIPANT_SAVE: " + str(e) + " "
                success = False
    if positive_value_exists(participant_entries_moved):
        try:
            ChallengeParticipant.objects.bulk_update(bulk_update_list, ['organization_we_vote_id', 'voter_we_vote_id'])
        except Exception as e:
            status += "FAILED_BULK_PARTICIPANT_SAVE: " + str(e) + " "
            success = False

    results = {
        'status':                           status,
        'success':                          success,
        'from_voter_we_vote_id':            from_voter_we_vote_id,
        'to_voter_we_vote_id':              to_voter_we_vote_id,
        'participant_entries_moved':        participant_entries_moved,
        'participant_entries_not_moved':    participant_entries_not_moved,
    }
    return results


def generate_challenge_participant_dict_from_challenge_participant_object(challenge_participant=None):
    status = ""
    success = True

    participant_dict = {
        'challenge_we_vote_id': '',
        'date_joined': '',
        'date_last_changed': '',
        'invitees_count': '',
        'invitees_who_joined': '',
        'invitees_who_viewed': '',
        'invitees_who_viewed_plus': '',
        'invite_text_for_friends': '',
        'organization_we_vote_id': '',
        'participant_id': 0,
        'participant_name': '',
        'points': '',
        'rank': '',
        'visible_to_public': '',
        'voter_we_vote_id': '',
        'we_vote_hosted_profile_image_url_medium': '',
        'we_vote_hosted_profile_image_url_tiny': '',
    }

    if not hasattr(challenge_participant, 'visible_to_public'):
        status += "VALID_CHALLENGE_PARTICIPANT_OBJECT_MISSING "
        results = {
            'challenge_participant_dict': participant_dict,
            'status': status,
            'success': False,
        }
        return results

    # If smaller sizes weren't stored, use large image
    if challenge_participant:
        if challenge_participant.we_vote_hosted_profile_image_url_medium:
            we_vote_hosted_profile_image_url_medium = challenge_participant.we_vote_hosted_profile_image_url_medium
        else:
            we_vote_hosted_profile_image_url_medium = ''
        if challenge_participant.we_vote_hosted_profile_image_url_tiny:
            we_vote_hosted_profile_image_url_tiny = challenge_participant.we_vote_hosted_profile_image_url_tiny
        else:
            we_vote_hosted_profile_image_url_tiny = we_vote_hosted_profile_image_url_medium
    else:
        we_vote_hosted_profile_image_url_medium = ''
        we_vote_hosted_profile_image_url_tiny = ''

    date_last_changed_string = ''
    date_joined_string = ''
    try:
        date_last_changed_string = challenge_participant.date_last_changed.strftime(DATE_FORMAT_YMD_HMS)
        date_joined_string = challenge_participant.date_joined.strftime(DATE_FORMAT_YMD_HMS)
    except Exception as e:
        status += "DATE_CONVERSION_ERROR: " + str(e) + " "
    participant_dict['challenge_we_vote_id'] = challenge_participant.challenge_we_vote_id
    participant_dict['date_joined'] = date_joined_string
    participant_dict['date_last_changed'] = date_last_changed_string
    participant_dict['invitees_count'] = challenge_participant.invitees_count
    participant_dict['invitees_who_joined'] = challenge_participant.invitees_who_joined
    participant_dict['invitees_who_viewed'] = challenge_participant.invitees_who_viewed
    participant_dict['invitees_who_viewed_plus'] = challenge_participant.invitees_who_viewed_plus
    participant_dict['invite_text_for_friends'] = challenge_participant.invite_text_for_friends
    participant_dict['organization_we_vote_id'] = challenge_participant.organization_we_vote_id
    participant_dict['participant_id'] = challenge_participant.id
    participant_dict['participant_name'] = challenge_participant.participant_name
    participant_dict['points'] = challenge_participant.points
    participant_dict['rank'] = challenge_participant.rank
    participant_dict['visible_to_public'] = challenge_participant.visible_to_public
    participant_dict['voter_we_vote_id'] = challenge_participant.voter_we_vote_id
    participant_dict['we_vote_hosted_profile_image_url_medium'] = we_vote_hosted_profile_image_url_medium
    participant_dict['we_vote_hosted_profile_image_url_tiny'] = we_vote_hosted_profile_image_url_tiny

    results = {
        'challenge_participant_dict':   participant_dict,
        'status':                       status,
        'success':                      success,
    }
    return results


def delete_challenge_participants_after_positions_removed(
        request,
        friends_only_positions=False,
        state_code=''):
    # Create default variables needed below
    challenge_participant_entries_deleted_count = 0
    challenge_we_vote_id_list_to_refresh = []
    number_to_delete = 20  # 1000
    from position.models import PositionEntered, PositionForFriends
    position_objects_to_set_challenge_participant_created_true = []  # Field is 'challenge_participant_created'
    position_updates_made = 0
    position_we_vote_id_list_to_remove_from_challenge_participants = []
    challenge_participant_id_list_to_delete = []
    status = ''
    success = True
    # timezone = pytz.timezone("America/Los_Angeles")
    # datetime_now = timezone.localize(datetime.now())
    # datetime_now = generate_localized_datetime_from_obj()[1]
    # date_today_as_integer = convert_date_to_date_as_integer(datetime_now)
    date_today_as_integer = get_current_date_as_integer()
    update_message = ''

    try:
        if positive_value_exists(friends_only_positions):
            position_query = PositionForFriends.objects.all()  # Cannot be readonly, since we bulk_update at the end
        else:
            position_query = PositionEntered.objects.all()  # Cannot be readonly, since we bulk_update at the end
        position_query = position_query.exclude(challenge_participant_created=True)
        position_query = position_query.exclude(stance=SUPPORT)
        position_query = position_query.filter(
            Q(position_ultimate_election_not_linked=True) |
            Q(position_ultimate_election_date__gte=date_today_as_integer)
        )
        if positive_value_exists(state_code):
            position_query = position_query.filter(state_code__iexact=state_code)
        total_to_convert = position_query.count()
        position_list_with_support_removed = list(position_query[:number_to_delete])
    except Exception as e:
        position_list_with_support_removed = []
        total_to_convert = 0
        update_message += "POSITION_LIST_WITH_SUPPORT_RETRIEVE_FAILED: " + str(e) + " "

    for one_position in position_list_with_support_removed:
        position_we_vote_id_list_to_remove_from_challenge_participants.append(one_position.we_vote_id)

    challenge_participant_search_success = True
    if len(position_we_vote_id_list_to_remove_from_challenge_participants) > 0:
        try:
            queryset = ChallengeParticipant.objects.using('readonly').all()
            queryset = queryset.filter(
                linked_position_we_vote_id__in=position_we_vote_id_list_to_remove_from_challenge_participants)
            challenge_participant_entries_to_delete = list(queryset)
            for one_challenge_participant in challenge_participant_entries_to_delete:
                challenge_participant_id_list_to_delete.append(one_challenge_participant.id)
        except Exception as e:
            challenge_participant_search_success = False
            update_message += "CHALLENGE_PARTICIPANT_RETRIEVE_BY_POSITION_WE_VOTE_ID-FAILED: " + str(e) + " "

    position_updates_needed = False
    if challenge_participant_search_success:
        # As long as there haven't been any errors above, we can prepare to mark
        #  all positions 'challenge_participant_created' = True
        for one_position in position_list_with_support_removed:
            one_position.challenge_participant_created = True
            position_objects_to_set_challenge_participant_created_true.append(one_position)
            position_updates_made += 1
            position_updates_needed = True

    challenge_participant_bulk_delete_success = True
    if len(challenge_participant_id_list_to_delete) > 0:
        try:
            queryset = ChallengeParticipant.objects.all()
            queryset = queryset.filter(id__in=challenge_participant_id_list_to_delete)
            challenge_participant_entries_deleted_count, challenges_dict = queryset.delete()
            challenge_participant_bulk_delete_success = True
            update_message += \
                "{challenge_participant_entries_deleted_count:,} ChallengeParticipant entries deleted, " \
                "".format(challenge_participant_entries_deleted_count=challenge_participant_entries_deleted_count)
        except Exception as e:
            challenge_participant_bulk_delete_success = False
            update_message += "CHALLENGE_PARTICIPANT_BULK_DELETE-FAILED: " + str(e) + " "

    if position_updates_needed and challenge_participant_bulk_delete_success:
        try:
            if friends_only_positions:
                PositionForFriends.objects.bulk_update(
                    position_objects_to_set_challenge_participant_created_true, ['challenge_participant_created'])
            else:
                PositionEntered.objects.bulk_update(
                    position_objects_to_set_challenge_participant_created_true, ['challenge_participant_created'])
            update_message += \
                "{position_updates_made:,} positions updated with challenge_participant_created=True, " \
                "".format(position_updates_made=position_updates_made)
        except Exception as e:
            messages.add_message(request, messages.ERROR,
                                 "ERROR with PositionEntered.objects.bulk_update: {e}, "
                                 "".format(e=e))

    total_to_convert_after = total_to_convert - number_to_delete if total_to_convert > number_to_delete else 0
    if positive_value_exists(total_to_convert_after):
        update_message += \
            "{total_to_convert_after:,} positions remaining in 'delete ChallengeParticipant' process. " \
            "".format(total_to_convert_after=total_to_convert_after)

    if positive_value_exists(update_message):
        messages.add_message(request, messages.INFO, update_message)

    results = {
        'challenge_participant_entries_deleted':  challenge_participant_entries_deleted_count,
        'challenge_we_vote_id_list_to_refresh': challenge_we_vote_id_list_to_refresh,
        'status':   status,
        'success':  success,
    }
    return results


def delete_challenge_participant(voter_to_delete=None):
    
    status = ""
    success = True
    challenge_participant_deleted = 0
    challenge_participant_not_deleted = 0
    voter_to_delete_id = voter_to_delete.we_vote_id

    if not positive_value_exists(voter_to_delete_id):
        status += "DELETE_CHALLENGE_PARTICIPANT-MISSING_VOTER_ID"
        success = False
        results = {
            'status':                           status,
            'success':                          success,
            'voter_to_delete_we_vote_id':       voter_to_delete_id,
            'challenge_participant_deleted':       challenge_participant_deleted,
            'challenge_participant_not_deleted':   challenge_participant_not_deleted,
        }
        return results
    
    try:
        number_deleted, details = ChallengeParticipant.objects\
            .filter(voter_we_vote_id=voter_to_delete_id, )\
            .delete()
        challenge_participant_deleted += number_deleted
    except Exception as e:
        status += "ChallengeParticipant CHALLENGE PARTICIPANT NOT DELETED: " + str(e) + " "
        challenge_participant_not_deleted += 1

    results = {
        'status':                           status,
        'success':                          success,
        'challenge_participant_deleted':      challenge_participant_deleted,
        'challenge_participant_not_deleted':  challenge_participant_not_deleted,
    }
    return results


def update_challenge_participant_entries_from_voter_object(voter_object=None):
    status = ""
    success = True

    voter_dict = {}
    voter_we_vote_id = voter_object.we_vote_id
    voter_dict[voter_we_vote_id] = voter_object

    try:
        queryset = ChallengeParticipant.objects.all()
        queryset = queryset.filter(voter_we_vote_id=voter_we_vote_id)
        challenge_participant_list = list(queryset)
    except Exception as e:
        status += "CHALLENGE_PARTICIPANT_LIST_RETRIEVE_ERROR: " + str(e) + " "
        results = {
            'status': status,
            'success': False,
            'challenge_participant_list': [],
            'voter_dict': voter_dict,
        }
        return results

    participants_with_data_changed_list = []
    for one_challenge_participant in challenge_participant_list:
        hydrate_results = hydrate_challenge_participant_object_from_voter_object(
            challenge_participant=one_challenge_participant,
            voter_dict=voter_dict,
        )
        if hydrate_results['success'] and hydrate_results['changes_found']:
            challenge_participant = hydrate_results['challenge_participant']
            participants_with_data_changed_list.append(challenge_participant)

    if len(participants_with_data_changed_list) > 0:
        try:
            rows_updated = ChallengeParticipant.objects.bulk_update(
                participants_with_data_changed_list,
                ['participant_name',
                 'we_vote_hosted_profile_image_url_medium', 'we_vote_hosted_profile_image_url_tiny'])
            status += "BULK_PARTICIPANT_UPDATES: " + str(rows_updated) + " "
        except Exception as e:
            status += "BULK_PARTICIPANT_UPDATE_FAILED: " + str(e)
            success = False
    results = {
        'status':                           status,
        'success':                          success,
    }
    return results


def hydrate_challenge_participant_object_from_voter_object(
            challenge_participant=None,
            voter_dict=None):
    changes_found = False
    status = ''
    success = True

    if challenge_participant and positive_value_exists(challenge_participant.id):
        pass
    else:
        status += "CHALLENGE_PARTICIPANT_NOT_FOUND "
        success = False
        results = {
            'challenge_participant':    None,
            'changes_found':            changes_found,
            'status':                   status,
            'success':                  success,
        }
        return results

    if voter_dict and challenge_participant.voter_we_vote_id in voter_dict:
        voter = voter_dict[challenge_participant.voter_we_vote_id]
    else:
        status += "VOTER_NOT_FOUND_IN_VOTER_DICT "
        success = False
        results = {
            'challenge_participant':    challenge_participant,
            'changes_found':            changes_found,
            'status':                   status,
            'success':                  success,
        }
        return results

    voter_full_name = voter.get_full_name(real_name_only=True)
    if positive_value_exists(voter_full_name) and challenge_participant.participant_name != voter_full_name:
        challenge_participant.participant_name = voter_full_name
        changes_found = True
    if positive_value_exists(voter.we_vote_hosted_profile_image_url_medium) and \
            challenge_participant.we_vote_hosted_profile_image_url_medium != \
            voter.we_vote_hosted_profile_image_url_medium:
        challenge_participant.we_vote_hosted_profile_image_url_medium = voter.we_vote_hosted_profile_image_url_medium
        changes_found = True
    if positive_value_exists(voter.we_vote_hosted_profile_image_url_tiny) and \
            challenge_participant.we_vote_hosted_profile_image_url_tiny != \
            voter.we_vote_hosted_profile_image_url_tiny:
        challenge_participant.we_vote_hosted_profile_image_url_tiny = voter.we_vote_hosted_profile_image_url_tiny
        changes_found = True

    results = {
        'status':                   status,
        'success':                  success,
        'challenge_participant':    challenge_participant,
        'changes_found':            changes_found,
    }
    return results


def refresh_participant_name_and_photo_for_challenge_participant_list(
        challenge_we_vote_id_list=[],
        challenge_participant_list=[],
        voter_dict=''):
    status = ''
    success = True

    if len(challenge_participant_list) == 0 and len(challenge_we_vote_id_list) > 0:
        try:
            queryset = ChallengeParticipant.objects.all()
            queryset = queryset.filter(challenge_we_vote_id__in=challenge_we_vote_id_list)
            challenge_participant_list = list(queryset)
        except Exception as e:
            status += "CHALLENGE_PARTICIPANT_LIST_RETRIEVE_ERROR: " + str(e) + " "
            results = {
                'status':                       status,
                'success':                      False,
                'challenge_participant_list':   [],
                'voter_dict':                   voter_dict,
            }
            return results

    # Retrieve voter data for all participants
    voter_we_vote_id_list = [challenge_participant.voter_we_vote_id
                             for challenge_participant in challenge_participant_list]
    queryset = Voter.objects.using('readonly').filter(we_vote_id__in=voter_we_vote_id_list)
    voter_list = list(queryset)
    voter_dict, results = generate_dict_from_list_with_key_from_one_attribute(
        incoming_list=voter_list, field_to_use_as_key='we_vote_id')

    participants_with_data_changed_list = []
    for challenge_participant in challenge_participant_list:
        hydrate_results = hydrate_challenge_participant_object_from_voter_object(
            challenge_participant=challenge_participant,
            voter_dict=voter_dict)
        if hydrate_results['success'] and hydrate_results['changes_found']:
            participants_with_data_changed_list.append(hydrate_results['challenge_participant'])
    if len(participants_with_data_changed_list) > 0:
        try:
            rows_updated = ChallengeParticipant.objects.bulk_update(
                participants_with_data_changed_list,
                ['participant_name',
                 'we_vote_hosted_profile_image_url_medium', 'we_vote_hosted_profile_image_url_tiny'])
            status += "BULK_PARTICIPANT_UPDATES: " + str(rows_updated) + " "
        except Exception as e:
            status += "BULK_PARTICIPANT_UPDATE_FAILED: " + str(e)
            success = False

    results = {
        'status':                       status,
        'success':                      success,
        'challenge_participant_list':   challenge_participant_list,
        'voter_dict':                   voter_dict,
    }
    return results


def update_challenge_participants_for_challenge_with_invitee_stats(
        challenge_we_vote_id=''):
    status = ""
    success = True
    try:
        queryset = ChallengeParticipant.objects.all()
        queryset = queryset.filter(challenge_we_vote_id=challenge_we_vote_id)
        queryset = queryset.values_list('voter_we_vote_id', flat=True).distinct()
        voter_we_vote_id_list = list(queryset)
    except Exception as e:
        status += "CHALLENGE_PARTICIPANT_LIST_RETRIEVE_ERROR: " + str(e) + " "
        results = {
            'status': status,
            'success': False,
        }
        return results

    try:
        queryset = Voter.objects.using('readonly').all()
        queryset = queryset.filter(we_vote_id__in=voter_we_vote_id_list)
        voter_list = list(queryset)
    except Exception as e:
        status += "VOTER_LIST_RETRIEVE_ERROR: " + str(e) + " "
        results = {
            'status': status,
            'success': False,
        }
        return results

    for voter in voter_list:
        challenge_results = update_challenge_participant_with_invitee_stats(
            challenge_we_vote_id=challenge_we_vote_id,
            inviter_voter=voter,
            inviter_voter_we_vote_id=voter.we_vote_id)
        status += challenge_results['status']

    # Now calculate and save invitees_who_viewed_plus
    for voter in voter_list:
        stats_results = update_challenge_participant_with_invitees_who_viewed_plus(
            challenge_we_vote_id=challenge_we_vote_id,
            inviter_voter_we_vote_id=voter.we_vote_id,
        )
        status += stats_results['status']

    results = {
        'status':   status,
        'success':  success,
    }
    return results


def update_challenge_participant_with_invitee_stats(
        challenge_we_vote_id='',
        inviter_voter=None,
        inviter_voter_we_vote_id=''):
    status = ""
    success = True

    from challenge.controllers_invitee import retrieve_invitee_stats_to_store_in_participant
    stats_results = retrieve_invitee_stats_to_store_in_participant(challenge_we_vote_id, inviter_voter_we_vote_id)
    if stats_results['success']:
        update_values = stats_results['update_values']
        # While here, make sure Participant name is up-to-date if a voter was passed in
        if inviter_voter and hasattr(inviter_voter, 'first_name'):
            voter_name = inviter_voter.get_full_name(real_name_only=True)
            if positive_value_exists(voter_name):
                update_values['participant_name'] = voter_name
        try:
            participants_updated = ChallengeParticipant.objects \
                .filter(
                    challenge_we_vote_id=challenge_we_vote_id,
                    voter_we_vote_id=inviter_voter_we_vote_id) \
                .update(**update_values)
            status += "UPDATED_INVITEE_STATS: " + str(participants_updated) + " "
        except Exception as e:
            status += "FAILED_UPDATE_INVITEE_STATS: " + str(e) + " "
            success = False

    results = {
        'status':   status,
        'success':  success,
    }
    return results


def update_challenge_participant_with_invitees_who_viewed_plus(
        challenge_we_vote_id='',
        inviter_voter_we_vote_id=''):
    status = ""
    success = True

    # invitees_who_viewed_plus must be calculated after all challenge participants
    # have been updated individually with invitee_stats.
    invitees_who_viewed_from_children = 0
    children_invitee_list = []
    if positive_value_exists(inviter_voter_we_vote_id):
        # Get a list of Participants who were invited by this voter (i.e., inviter_voter_we_vote_id).
        try:
            queryset = ChallengeParticipant.objects.using('readonly').all()
            queryset = queryset.filter(challenge_we_vote_id=challenge_we_vote_id)
            queryset = queryset.filter(inviter_voter_we_vote_id=inviter_voter_we_vote_id)
            children_invitee_list = list(queryset)
        except Exception as e:
            status += "FAILED_RETRIEVING_PARTICIPANT_LIST_FOR_WHO_VIEWED: " + str(e) + ' '
            success = False

    for invitee_child in children_invitee_list:
        invitees_who_viewed_from_children += invitee_child.invitees_who_viewed

    # Update even if invitees_who_viewed_from_children is zero, so we can update
    #  invitees_who_viewed_plus to match invitees_who_viewed
    try:
        queryset = ChallengeParticipant.objects.all()
        queryset = queryset.filter(challenge_we_vote_id=challenge_we_vote_id)
        queryset = queryset.filter(voter_we_vote_id=inviter_voter_we_vote_id)
        update_count = queryset.update(
            invitees_who_viewed_plus=F('invitees_who_viewed') + invitees_who_viewed_from_children)
        if update_count > 0:
            pass
    except Exception as e:
        status += "CHALLENGE_PARTICIPANT_WHO_VIEWED_PLUS_UPDATE_FAILED: " + str(e) + " "

    results = {
        'status':   status,
        'success':  success,
    }
    return results
