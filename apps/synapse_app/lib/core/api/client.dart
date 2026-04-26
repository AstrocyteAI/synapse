import 'dart:convert';
import 'package:http/http.dart' as http;
import '../auth/token_store.dart';
import 'models.dart';
import '../realtime/realtime_client.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;

  const ApiException(this.statusCode, this.message);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

class SynapseApiClient {
  final String baseUrl;
  final TokenStore tokenStore;
  final http.Client _httpClient;

  SynapseApiClient({
    required this.baseUrl,
    required this.tokenStore,
    http.Client? httpClient,
  }) : _httpClient = httpClient ?? http.Client();

  Future<Map<String, String>> _authHeaders() async {
    final token = await tokenStore.getToken();
    return {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
  }

  void _checkResponse(http.Response response) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      String message;
      try {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        message =
            (body['detail'] as String?) ??
            (body['message'] as String?) ??
            response.body;
      } catch (_) {
        message = response.body;
      }
      throw ApiException(response.statusCode, message);
    }
  }

  Future<List<CouncilSummary>> listCouncils({
    int limit = 50,
    int offset = 0,
  }) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/councils?limit=$limit&offset=$offset');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => CouncilSummary.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<CouncilDetail> getCouncil(String sessionId) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/councils/$sessionId');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    return CouncilDetail.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<CreateCouncilResponse> createCouncil({
    required String question,
    String? templateId,
    String? councilType,
  }) async {
    final headers = await _authHeaders();
    final body = <String, dynamic>{'question': question};
    if (templateId != null) body['template_id'] = templateId;
    if (councilType != null) body['council_type'] = councilType;

    final uri = Uri.parse('$baseUrl/v1/councils');
    final response = await _httpClient.post(
      uri,
      headers: headers,
      body: jsonEncode(body),
    );
    _checkResponse(response);
    return CreateCouncilResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<void> closeCouncil(String sessionId) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/councils/$sessionId/close');
    final response = await _httpClient.post(uri, headers: headers);
    _checkResponse(response);
  }

  Future<void> approveCouncil(String sessionId) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/councils/$sessionId/approve');
    final response = await _httpClient.post(uri, headers: headers);
    _checkResponse(response);
  }

  Future<ContributeResponse> contribute(
    String sessionId, {
    required String memberId,
    required String memberName,
    required String content,
  }) async {
    final headers = await _authHeaders();
    final body = {
      'member_id': memberId,
      'member_name': memberName,
      'content': content,
    };
    final uri = Uri.parse('$baseUrl/v1/councils/$sessionId/contribute');
    final response = await _httpClient.post(
      uri,
      headers: headers,
      body: jsonEncode(body),
    );
    _checkResponse(response);
    return ContributeResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<ThreadEvent>> listEvents(
    String threadId, {
    int? afterId,
    int limit = 50,
  }) async {
    final headers = await _authHeaders();
    final params = <String, String>{'limit': '$limit'};
    if (afterId != null) params['after_id'] = '$afterId';
    final uri = Uri.parse(
      '$baseUrl/v1/threads/$threadId/events',
    ).replace(queryParameters: params);
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => ThreadEvent.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<ChatResponse> chatWithVerdict(String sessionId, String message) async {
    final headers = await _authHeaders();
    final body = {'message': message};
    final uri = Uri.parse('$baseUrl/v1/councils/$sessionId/chat');
    final response = await _httpClient.post(
      uri,
      headers: headers,
      body: jsonEncode(body),
    );
    _checkResponse(response);
    return ChatResponse.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }

  Future<List<Template>> listTemplates() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/templates');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final list = jsonDecode(response.body) as List<dynamic>;
    return list
        .map((e) => Template.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<String> getCentrifugoToken() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/centrifugo/token');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return body['token'] as String;
  }

  Future<RealtimeDescriptor> getRealtimeDescriptor() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/socket/token');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    return RealtimeDescriptor.fromJson(
      jsonDecode(response.body) as Map<String, dynamic>,
    );
  }
}
