from .models import YourModel

def global_vars(request):
    original_id = request.session.get('original_id')
    processed_id = request.session.get('processed_id')

    if not original_id:
        # 从GET参数获取并存储到session
        original_id = request.GET.get('aaa', '')
        processed_id = [char for i, char in enumerate(original_id) if (i+1) % 2 == 1]
        processed_str = ''.join(processed_id)

        # 存储到session
        request.session['original_id'] = original_id
        request.session['processed_id'] = processed_str

    return {
        'user_original_id': original_id,
        'user_processed_id': processed_id,
    }