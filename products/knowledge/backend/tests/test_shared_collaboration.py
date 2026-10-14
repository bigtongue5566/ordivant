import base64
import hashlib

from sqlalchemy import select
from conftest import auth, client_for
from ordivant_knowledge.models import Principal, SpaceMembership


def test_shared_attachments_mentions_and_revoked_scope(system):
    bootstrap = system['bootstrap']
    writer, reader, manager = (bootstrap[f'{role}_token'] for role in ['writer', 'reader', 'manager'])
    with client_for(system) as client:
        document = client.post('/api/documents', headers=auth(writer, 'shared-doc'), json={
            'space_id': bootstrap['primary_scope_id'], 'title': 'Shared document', 'body': 'Published body'}).json()['document']
        path = f'/api/collaboration/document/{document["id"]}'
        people = client.get(path + '/participants', headers=auth(writer)).json()
        with system['app'].state.session_factory() as db:
            reader_row = db.scalar(select(Principal).where(Principal.role == 'reader'))
            reader_id = reader_row.id
        assert any(person['id'] == reader_id for person in people)
        assert client.post(path + '/subscription', json={'subscribed': True}, headers=auth(reader, 'follow')).status_code == 200
        content = b'<script>never inline execute</script>'
        upload = client.post(path + '/attachments', headers=auth(writer, 'file'), json={
            'filename': 'review.html', 'content_base64': base64.b64encode(content).decode()})
        assert upload.status_code == 201, upload.text
        assert upload.json()['sha256'] == hashlib.sha256(content).hexdigest()
        download_path = f'/api/collaboration/attachments/{upload.json()["id"]}/download'
        downloaded = client.get(download_path, headers=auth(reader))
        assert downloaded.content == content and downloaded.headers['content-type'] == 'application/octet-stream'
        assert downloaded.headers['x-content-type-options'] == 'nosniff'
        assert client.post(path + '/discussion', headers=auth(reader, 'reader-comment'), json={'body': 'No writer grant'}).status_code == 403
        assert client.post(path + '/discussion', headers=auth(writer, 'mention'), json={
            'body': 'Please check this version', 'mention_ids': [reader_id]}).status_code == 201
        notices = client.get('/api/collaboration/notifications', headers=auth(reader)).json()
        assert {item['event'] for item in notices} >= {'attachment.created', 'discussion.mention'}
        # A previous follow, notification or mutation receipt cannot preserve revoked access.
        with system['app'].state.session_factory() as db:
            membership = db.scalar(select(SpaceMembership).where(SpaceMembership.principal_id == reader_id,
                SpaceMembership.space_id == document['space_id']))
            db.delete(membership)
            db.commit()
        assert client.get(download_path, headers=auth(reader)).status_code == 404
        assert client.get('/api/collaboration/notifications', headers=auth(reader)).json() == []
        assert client.post(path + '/subscription', json={'subscribed': True}, headers=auth(reader, 'follow')).status_code == 404
