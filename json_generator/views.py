import json
from django.db import connection, connections
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseBadRequest, Http404
import psycopg2

# --- 1단계: 시작 페이지 ---
def start_view(request):
    request.session.flush()
    if request.method == 'POST':
        request.session['use_default_db'] = True
        return redirect('json_generator:select_info_type') # 네임스페이스 추가
    return render(request, 'json_generator/start.html')


# --- 1-2단계: 새 DB 정보 입력 및 테스트 ---
def get_db_info_view(request):
    form_data = request.session.get('db_info_form', {})
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        current_input = {
            'host': request.POST.get('host'),
            'port': request.POST.get('port'),
            'dbname': request.POST.get('dbname'),
            'user': request.POST.get('user'),
            'password': request.POST.get('password'),
            'client_encoding': 'UTF8',
        }
        request.session['db_info_form'] = {k: v for k, v in current_input.items() if k != 'password'}

        if action == 'test':
            try:
                conn_test = psycopg2.connect(**current_input)
                conn_test.close()
                return render(request, 'json_generator/get_db_info.html', {
                    'test_success': "✅ DB 연결 성공!", 
                    'db_info': current_input
                })
            except Exception as e:
                return render(request, 'json_generator/get_db_info.html', {
                    'error': f"❌ DB 연결에 실패했습니다: {e}", 
                    'db_info': current_input
                })
        
        elif action == 'save':
            request.session['db_info'] = {
                'HOST': current_input['host'],
                'PORT': current_input['port'],
                'NAME': current_input['dbname'],
                'USER': current_input['user'],
                'PASSWORD': current_input['password'],
            }
            request.session['use_default_db'] = False
            return redirect('json_generator:select_info_type') # 네임스페이스 추가

    return render(request, 'json_generator/get_db_info.html', {'db_info': form_data})

# --- 헬퍼 함수: 현재 요청에 맞는 DB 연결을 가져옴 ---
def get_current_connection(request):
    if request.session.get('use_default_db'):
        return connection
    
    db_info = request.session.get('db_info')
    if not db_info:
        raise Http404("DB 연결 정보가 세션에 없습니다. 시작 페이지부터 다시 진행해주세요.")

    db_alias = 'dynamic_db'
    connections.databases[db_alias] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': db_info['NAME'], 
        'USER': db_info['USER'],
        'PASSWORD': db_info['PASSWORD'],
        'HOST': db_info['HOST'], 
        'PORT': db_info['PORT'],
        'ATOMIC_REQUESTS': False, 'AUTOCOMMIT': True,
        'TIME_ZONE': None, 'CONN_HEALTH_CHECKS': False,
        'CONN_MAX_AGE': 0, 'OPTIONS': {'client_encoding': 'UTF8'},
    }
    return connections[db_alias]

# --- 2단계: 정보 유형 선택 ---
def select_info_type_view(request):
    if request.method == 'GET':
        if 'config_data' in request.session:
            del request.session['config_data']
        if 'flow_type' in request.session:
            del request.session['flow_type']
        return render(request, 'json_generator/select_info_type.html')

    if request.method == 'POST':
        info_type = request.POST.get('mode')

        if info_type == 'new':
            request.session['config_data'] = {'mode': 'en'}
            request.session['flow_type'] = 'new'
            return redirect('json_generator:select_table_algo') # 네임스페이스 추가
        elif info_type == 'old':
            request.session['flow_type'] = 'old'
            return redirect('json_generator:select_mode') # 네임스페이스 추가
    
    return redirect('json_generator:start') # 네임스페이스 추가

# --- 2.5단계: 암/복호화 모드 선택 ---
def select_mode_view(request):
    if request.method == 'POST':
        request.session['config_data'] = {'mode': request.POST.get('mode')}
        return redirect('json_generator:select_table_algo') # 네임스페이스 추가
    if 'config_data' in request.session:
        del request.session['config_data']
    return render(request, 'json_generator/select_mode.html')

# --- 3단계: 테이블 및 알고리즘 선택 ---
def select_table_algo_view(request):
    try:
        current_connection = get_current_connection(request)
        with current_connection.cursor() as cursor:
            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            all_public_tables = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        if not request.session.get('use_default_db'):
            return render(request, 'json_generator/get_db_info.html', {'error': f"DB 연결 실패: {e}"})
        raise Http404(f"기본 DB 연결 실패: {e}")
    
    config_data = request.session.get('config_data', {})
    mode = config_data.get('mode')
    if not mode: return redirect('json_generator:select_info_type') # 네임스페이스 추가

    excluded_prefixes = ['auth_', 'django_']
    user_tables = [table for table in all_public_tables if not any(table.startswith(prefix) for prefix in excluded_prefixes)]
    algorithms = ['hight_ctr', 'hight_cbc']

    if request.method == 'POST':
        config_data['table'] = request.POST.get('table_name')
        if mode == 'en': config_data['algo'] = request.POST.get('algo')
        request.session['config_data'] = config_data
        
        flow_type = request.session.get('flow_type')
        
        if flow_type == 'new':
            return redirect('json_generator:insert_info') # 네임스페이스 추가
        else:
            return redirect('json_generator:select_columns_filter') # 네임스페이스 추가

    context = {'table_names': user_tables, 'algorithms': algorithms, 'mode': mode}
    return render(request, 'json_generator/select_table_algo.html', context)

# --- 4단계: 새로운 정보에 대한 처리 및 JSON 생성 ---
def insert_info_view(request):
    config_data = request.session.get('config_data', {})
    table_name = config_data.get('table')
    if not table_name:
        return redirect('json_generator:select_info_type') # 네임스페이스 추가

    try:
        current_connection = get_current_connection(request)
        with current_connection.cursor() as cursor:
            safe_table_name = current_connection.schema_editor().quote_name(table_name)
            cursor.execute(f"SELECT * FROM {safe_table_name} LIMIT 0")
            all_columns = [col[0] for col in cursor.description]
    except Exception as e:
        raise Http404(f"'{table_name}' 테이블 컬럼 조회 중 오류: {e}")

    excluded_input_columns = ['uuid', 'en_col', 'iv_data', 'encryption_algo']
    input_columns = [col for col in all_columns if col not in excluded_input_columns]

    if request.method == 'POST':
        # 1. 암호화 대상 컬럼 목록 가져오기
        selected_columns = request.POST.getlist('columns')
        
        # 2. [추가] 패스워드 해시 정보 가져오기
        password_hash_column = request.POST.get('password_hash_column')
        password_hash_algorithm = request.POST.get('password_hash_algorithm')

        # 3. [추가] 패스워드 해시 컬럼을 암호화 대상에서 제외
        if password_hash_column and password_hash_column in selected_columns:
            selected_columns.remove(password_hash_column)
        
        # 4. 사용자가 입력한 Row 데이터 수집 (기존 로직)
        all_rows_data = []
        row_index = 0
        while True:
            # ...
            if not input_columns or f'row-{row_index}-{input_columns[0]}' not in request.POST:
                break
            current_row_data = {col: request.POST.get(f'row-{row_index}-{col}', '') for col in input_columns}
            all_rows_data.append(current_row_data)
            row_index += 1

        # 5. 최종 JSON 생성
        json_list = []
        for row_data in all_rows_data:
            # 기본 JSON 구조 생성
            final_json = {
                "info_type": request.session.get('flow_type'),
                "mode": "en",
                "table": config_data.get('table'),
                "algo": config_data.get('algo'),
                "col": ", ".join(selected_columns), # 제외 처리가 끝난 컬럼 목록 사용
                "update": "T",
                "data": row_data
            }
            
            # [핵심] 패스워드 정보가 있으면 JSON에 'password' 키 추가
            if password_hash_column and password_hash_algorithm:
                final_json['password'] = {
                    "pass_algo": password_hash_algorithm,
                    "value": row_data.get(password_hash_column), # 사용자가 입력한 값
                    "column": password_hash_column
                }
            
            json_list.append(final_json)

        json_output = json.dumps(json_list, indent=4, ensure_ascii=False)
        return render(request, 'json_generator/display_json.html', {'json_data': json_output})

    context = { 'table_name': table_name, 'input_columns': input_columns }
    return render(request, 'json_generator/insert_info.html', context)


# --- 4단계: 기존 정보에 대한 처리 ---
def select_columns_filter_view(request):
    config_data = request.session.get('config_data', {})
    table_name = config_data.get('table')
    if not table_name: return redirect('json_generator:select_info_type') # 네임스페이스 추가

    try:
        current_connection = get_current_connection(request)
        with current_connection.cursor() as cursor:
            primary_key_column = current_connection.introspection.get_primary_key_column(cursor, table_name)
            if not primary_key_column:
                raise Http404(f"'{table_name}' 테이블에 Primary Key가 없어 Row를 특정할 수 없습니다.")
            safe_table_name = current_connection.schema_editor().quote_name(table_name)
            cursor.execute(f"SELECT * FROM {safe_table_name} ORDER BY {primary_key_column} asc")
            all_columns = [col[0] for col in cursor.description]
            all_rows = cursor.fetchall()
    except Exception as e:
        raise Http404(f"'{table_name}' 테이블 데이터 조회 중 오류: {e}")

    excluded_display_columns = ['uuid', 'en_col', 'iv_data', 'encryption_algo']
    display_columns = [col for col in all_columns if col not in excluded_display_columns]
    pk_index = all_columns.index(primary_key_column)
    processed_rows = [{'pk_value': row[pk_index], 'values': row} for row in all_rows]

    if request.method == 'POST':
        # 1. 사용자가 암호화 대상으로 선택한 컬럼 목록을 가져옵니다.
        selected_columns = request.POST.getlist('columns')
        
        # 2. 사용자가 패스워드 해시 대상으로 선택한 컬럼을 가져옵니다.
        password_hash_column = request.POST.get('password_hash_column')

        # [핵심] 만약 패스워드 해시 컬럼이 암호화 대상 목록에 포함되어 있다면, 여기서 제거합니다.
        if password_hash_column and password_hash_column in selected_columns:
            selected_columns.remove(password_hash_column)

        # 3. 이제 "깨끗해진" 컬럼 목록을 config_data에 저장합니다.
        config_data = request.session.get('config_data', {})
        config_data['columns'] = selected_columns
        
        # --- 나머지 기존 로직 ---
        config_data['filter_column'] = primary_key_column # (코드 순서상 primary_key_column이 먼저 정의되어야 함)
        config_data['filter_values'] = request.POST.getlist('selected_pk_values')
        
        password_hash_algorithm = request.POST.get('password_hash_algorithm')

        if password_hash_column and password_hash_algorithm:
            config_data['password_hash_info'] = {
                'column': password_hash_column,
                'algorithm': password_hash_algorithm
            }
        
        config_data['all_columns_list'] = all_columns
        request.session['config_data'] = config_data
        
        return redirect('json_generator:generate_config_json')

    context = {
        'table_name': table_name,
        'all_columns': all_columns,
        'display_columns': display_columns,
        'processed_rows': processed_rows,
    }
    return render(request, 'json_generator/select_columns_filter.html', context)


# --- 5단계: 최종 JSON 생성 (기존 정보 전용) ---
def generate_config_json_view(request):
    config_data = request.session.get('config_data')
    if not config_data:
        return redirect('json_generator:select_info_type') # 네임스페이스 추가

    if request.method == 'POST':
        pk_values = config_data.get('filter_values', [])
        filter_column = config_data.get('filter_column')
        password_info = config_data.get('password_hash_info')
        all_columns = config_data.get('all_columns_list', [])

        rows_map = {}
        if password_info and pk_values:
            current_connection = get_current_connection(request)
            with current_connection.cursor() as cursor:
                safe_table_name = current_connection.schema_editor().quote_name(config_data['table'])
                placeholders = ','.join(['%s'] * len(pk_values))
                query = f"SELECT * FROM {safe_table_name} WHERE {filter_column} IN ({placeholders})"
                cursor.execute(query, tuple(pk_values))
                pk_index = all_columns.index(filter_column)
                rows_map = {str(row[pk_index]): dict(zip(all_columns, row)) for row in cursor.fetchall()}

        json_list = []
        for pk_value in pk_values:
            final_json = {
                "info_type": request.session.get('flow_type'),
                "mode": config_data.get('mode'),
                "table": config_data.get('table'),
                filter_column: pk_value,
                "col": ", ".join(config_data.get('columns', [])),
                "update": request.POST.get('update_db', 'F')
            }
            if final_json['mode'] == 'en':
                final_json['algo'] = config_data.get('algo')
            
            if password_info and str(pk_value) in rows_map:
                row_data = rows_map[str(pk_value)]
                password_col_name = password_info['column']
                
                final_json['password'] = {
                    "pass_algo": password_info['algorithm'],
                    "value": row_data.get(password_col_name),
                    "column": password_col_name
                }
            
            json_list.append(final_json)

        json_output = json.dumps(json_list, indent=4, ensure_ascii=False)
        return render(request, 'json_generator/display_json.html', {'json_data': json_output})

    return render(request, 'json_generator/select_update.html')



# --- (참고) 독립적인 패스워드 해시 테스트용 뷰 ---
def process_password_hash_view(request):
    if request.method == 'POST':
        password_column = request.POST.get('password_column')
        hash_algorithm = request.POST.get('hash_algorithm')
        selected_pks = request.POST.getlist('selected_pks_for_hash')

        if not all([password_column, hash_algorithm, selected_pks]):
            return HttpResponseBadRequest("필수 데이터가 누락되었습니다.")

        data_to_be_json = {
            "target_column": password_column,
            "algorithm": hash_algorithm,
            "pks_to_hash": selected_pks
        }
        return JsonResponse(data_to_be_json)

    return JsonResponse({'error': 'POST request required.'}, status=405)