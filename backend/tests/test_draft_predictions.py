"""Save/Submit acceptance for undoable AI drafts, using isolated test data only."""
import pytest
from .test_api import client, project
from .test_auto_label import upload, mock_infer
from .test_workspaces import people, team, role


def setup_predictions(monkeypatch):
    monkeypatch.setattr('app.services.auto_label_service.yolo_service.infer', mock_infer)
    p = project(); image = upload(p['id'], 'draft-predictions.png')
    predictions = client.post(f'/api/images/{image["id"]}/auto-label', json={}).json()['predictions']
    return p, image, predictions


def draft(prediction, **changes):
    return dict(class_id=prediction['mapped_class_id'] or 0, annotation_type=prediction['prediction_type'],
                x=prediction['x'], y=prediction['y'], width=prediction['width'], height=prediction['height'],
                points=prediction['points'], prediction_id=prediction['id'], prediction_token=prediction['draft_token'], **changes)


def test_ai_drafts_only_persist_on_save_with_provenance_and_one_revision(monkeypatch):
    p, image, predictions = setup_predictions(monkeypatch)
    assert client.get(f'/api/images/{image["id"]}/annotations').json() == []
    assert client.get(f'/api/projects/{p["id"]}/classes').json() == []
    before = client.get(f'/api/images/{image["id"]}/review').json()
    response = client.put(f'/api/images/{image["id"]}/annotations', json={
        'items': [draft(item) for item in predictions], 'expected_versions': {}, 'expected_revision': before['revision']})
    assert response.status_code == 200, response.text
    rows = response.json(); assert len(rows) == 2
    assert {row['class_name'] for row in rows} == {'car', 'person'}
    assert all(row['source'] == 'ai_accepted' and row['created_by'] and row['created_by'] == row['updated_by'] for row in rows)
    assert client.get(f'/api/images/{image["id"]}/review').json()['revision'] == before['revision'] + 1
    assert all(p['status'] == 'ACCEPTED' for p in client.get(f'/api/images/{image["id"]}/predictions').json())
    # A repeated stale Save must not duplicate AI objects.
    repeated = client.put(f'/api/images/{image["id"]}/annotations', json={'items': [draft(item) for item in predictions], 'expected_versions': {}})
    assert repeated.status_code == 409
    assert len(client.get(f'/api/images/{image["id"]}/annotations').json()) == 2


def test_undo_before_save_leaves_ai_pending_and_does_not_create_classes(monkeypatch):
    p, image, predictions = setup_predictions(monkeypatch)
    response = client.put(f'/api/images/{image["id"]}/annotations', json={'items': [], 'expected_versions': {}})
    assert response.status_code == 200 and response.json() == []
    assert client.get(f'/api/projects/{p["id"]}/classes').json() == []
    assert all(p['status'] == 'PENDING' for p in client.get(f'/api/images/{image["id"]}/predictions').json())


def test_ai_edited_draft_keeps_actual_actor_and_saved_geometry(monkeypatch):
    p, image, predictions = setup_predictions(monkeypatch)
    label = client.post(f'/api/projects/{p["id"]}/classes', json={'name': 'Custom'}).json()
    item = draft(predictions[0]); item.update(class_id=label['id'], x=12, width=30, created_by={'id': 'spoof'}, source='manual')
    response = client.put(f'/api/images/{image["id"]}/annotations', json={'items': [item], 'expected_versions': {}})
    assert response.status_code == 200, response.text
    saved = response.json()[0]
    assert saved['source'] == 'ai_edited' and saved['class_id'] == label['id']
    assert saved['x'] == 12 and saved['width'] == 30 and saved['created_by']['id'] != 'spoof'


@pytest.mark.parametrize('invalid', ['token', 'duplicate', 'foreign', 'geometry', 'deleted_prediction'])
def test_failed_ai_save_rolls_back_whole_batch_and_new_classes(monkeypatch, invalid):
    p, image, predictions = setup_predictions(monkeypatch)
    items = [draft(p) for p in predictions]
    if invalid == 'token': items[1]['prediction_token'] = 'stale'
    if invalid == 'duplicate': items[1] = items[0].copy()
    if invalid == 'foreign':
        other = upload(p['id'], 'other-draft.png')
        foreign = client.post(f'/api/images/{other["id"]}/auto-label', json={}).json()['predictions'][0]
        items[1] = draft(foreign)
    if invalid == 'geometry': items[1]['width'] = 1000
    if invalid == 'deleted_prediction':
        client.post(f'/api/images/{image["id"]}/auto-label', json={})
    response = client.put(f'/api/images/{image["id"]}/annotations', json={'items': items, 'expected_versions': {}})
    assert response.status_code in (400, 409), response.text
    assert client.get(f'/api/images/{image["id"]}/annotations').json() == []
    assert client.get(f'/api/projects/{p["id"]}/classes').json() == []
    assert all(p['status'] == 'PENDING' for p in client.get(f'/api/images/{image["id"]}/predictions').json())


def test_submit_accepts_ai_draft_atomically_and_locks_image(monkeypatch):
    p, image, predictions = setup_predictions(monkeypatch)
    review = client.get(f'/api/images/{image["id"]}/review').json()
    response = client.post(f'/api/images/{image["id"]}/review/submit', json={
        'expected_revision': review['revision'], 'expected_review_version': review['review_version'],
        'negative_confirmed': False, 'annotations': {'items': [draft(predictions[0])], 'expected_versions': {}}})
    assert response.status_code == 200, response.text
    assert response.json()['annotations'][0]['source'] == 'ai_accepted'
    assert response.json()['review']['state'] == 'pending_review'


def test_ai_batch_cannot_bypass_object_delete_permissions(team, monkeypatch):
    owner, member, _, _, _, p, label, image, annotation = team
    role(team, 'annotator')
    monkeypatch.setattr('app.services.auto_label_service.yolo_service.infer', mock_infer)
    prediction = member[0].post(f'/api/images/{image["id"]}/auto-label', json={}).json()['predictions'][0]
    endpoint = f'/api/images/{image["id"]}/annotations'
    # Omitting the owner's protected object still requires permission to delete it.
    payload = {'expected_versions': {str(annotation['id']): annotation['version']}, 'items': [draft(prediction)]}
    assert member[0].put(endpoint, json=payload).status_code == 403
    assert len(owner[0].get(endpoint).json()) == 1
    payload['items'].insert(0, {key: annotation[key] for key in ('id','class_id','annotation_type','x','y','width','height','points')})
    response = member[0].put(endpoint, json=payload)
    assert response.status_code == 200, response.text
    restored = next(a for a in response.json() if a['id'] == annotation['id'])
    assert restored['created_by'] == annotation['created_by'] and restored['version'] == annotation['version']
    assert next(a for a in response.json() if a['id'] != annotation['id'])['created_by']['id'] == member[2]['id']


def test_ai_batch_requires_prediction_review_permission(monkeypatch):
    from app.services.rbac import ROLE_PERMISSIONS
    p, image, predictions = setup_predictions(monkeypatch)
    monkeypatch.setitem(ROLE_PERMISSIONS, 'owner', ROLE_PERMISSIONS['owner'] - {'prediction.review'})
    response = client.put(f'/api/images/{image["id"]}/annotations', json={
        'expected_versions': {}, 'items': [draft(predictions[0])]})
    assert response.status_code == 403
    assert client.get(f'/api/images/{image["id"]}/annotations').json() == []
