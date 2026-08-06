import hashlib
import hmac
import json
import logging
import subprocess

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


def _verify_signature(request):
    secret = getattr(settings, 'GITHUB_WEBHOOK_SECRET', '')
    if not secret:
        return False
    signature = request.META.get('HTTP_X_HUB_SIGNATURE_256', '')
    if not signature.startswith('sha256='):
        return False
    expected = 'sha256=' + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@csrf_exempt
@require_POST
def github_data_sync_webhook(request):
    """
    Called by a GitHub webhook on every push to this repo. Fetches from
    origin and, if db.sqlite3 changed, checks out ONLY that one file -
    never a full `git pull`, so app code here is never affected by
    whatever else is on GitHub.
    """
    if not _verify_signature(request):
        return HttpResponseForbidden('invalid signature')

    event = request.META.get('HTTP_X_GITHUB_EVENT', '')
    if event == 'ping':
        return JsonResponse({'status': 'pong'})
    if event != 'push':
        return JsonResponse({'status': 'ignored', 'event': event})

    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'status': 'error', 'detail': 'invalid JSON'}, status=400)

    if payload.get('ref') != 'refs/heads/main':
        return JsonResponse({'status': 'ignored', 'ref': payload.get('ref')})

    repo_dir = str(settings.BASE_DIR)
    try:
        subprocess.run(
            ['git', 'config', '--global', '--add', 'safe.directory', repo_dir],
            check=False, timeout=10,
        )
        # --depth=1 keeps this a shallow clone forever - without it, every
        # fetch that picks up new upstream commits permanently grows this
        # repo's local .git history (each commit carries a multi-MB copy of
        # db.sqlite3), which previously filled the disk quota entirely and
        # broke every webhook call with "git fetch ... Disk quota exceeded".
        subprocess.run(
            ['git', 'fetch', '--depth=1', 'origin', 'main'],
            cwd=repo_dir, check=True, timeout=30, capture_output=True,
        )

        remote_hash = subprocess.run(
            ['git', 'rev-parse', 'origin/main:db.sqlite3'],
            cwd=repo_dir, check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        local_hash = subprocess.run(
            ['git', 'hash-object', 'db.sqlite3'],
            cwd=repo_dir, check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()

        if remote_hash != local_hash:
            subprocess.run(
                ['git', 'checkout', 'origin/main', '--', 'db.sqlite3'],
                cwd=repo_dir, check=True, timeout=15, capture_output=True,
            )
            logger.info('github_data_sync_webhook: db.sqlite3 updated %s -> %s', local_hash, remote_hash)
            return JsonResponse({'status': 'updated', 'from': local_hash, 'to': remote_hash})

        return JsonResponse({'status': 'unchanged', 'hash': local_hash})
    except subprocess.CalledProcessError as e:
        logger.exception('github_data_sync_webhook failed')
        detail = e.stderr.decode() if e.stderr else str(e)
        return JsonResponse({'status': 'error', 'detail': detail}, status=500)
