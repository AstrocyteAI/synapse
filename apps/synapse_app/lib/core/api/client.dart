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
  // Non-final: updated when the user switches server without a full app restart.
  String baseUrl;

  // Cerebro wraps every REST response in {"data": ...}.  Set true when the
  // live server is a Cerebro backend so _unwrap/_unwrapList strip the envelope.
  bool isCerebro;

  final TokenStore tokenStore;
  final http.Client _httpClient;

  SynapseApiClient({
    required this.baseUrl,
    required this.tokenStore,
    this.isCerebro = false,
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

  /// Strips Cerebro's `{"data": {...}}` envelope for single-object responses.
  Map<String, dynamic> _unwrap(Map<String, dynamic> body) {
    if (isCerebro) {
      final data = body['data'];
      if (data is Map<String, dynamic>) return data;
    }
    return body;
  }

  /// Strips Cerebro's `{"data": [...]}` envelope for list responses.
  List<dynamic> _unwrapList(dynamic decoded) {
    if (isCerebro && decoded is Map<String, dynamic>) {
      final data = decoded['data'];
      if (data is List) return data;
    }
    if (decoded is List) return decoded;
    return const [];
  }

  Future<List<CouncilSummary>> listCouncils({
    int limit = 50,
    int offset = 0,
  }) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/councils?limit=$limit&offset=$offset');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final list = _unwrapList(jsonDecode(response.body));
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
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
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
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
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
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
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
    final list = _unwrapList(jsonDecode(response.body));
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
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }

  Future<List<Template>> listTemplates() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/templates');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final list = _unwrapList(jsonDecode(response.body));
    return list
        .map((e) => Template.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  Future<String> getCentrifugoToken() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/centrifugo/token');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final body = _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
    return body['token'] as String;
  }

  Future<RealtimeDescriptor> getRealtimeDescriptor() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/socket/token');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    return RealtimeDescriptor.fromJson(
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }

  // ─── Backend metadata (X-2) — public, no auth ─────────────────────────────

  Future<BackendInfo> getBackendInfo() async {
    final uri = Uri.parse('$baseUrl/v1/info');
    final response = await _httpClient.get(uri);
    _checkResponse(response);
    final raw = jsonDecode(response.body) as Map<String, dynamic>;
    // Cerebro wraps /v1/info too — strip the envelope before parsing.
    final body = raw['data'] is Map<String, dynamic>
        ? raw['data'] as Map<String, dynamic>
        : raw;
    return BackendInfo.fromJson(body);
  }

  // ─── Notifications (B10 / W9 / F3) ────────────────────────────────────────

  Future<NotificationPreferences> getNotificationPreferences() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/notifications/preferences');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    return NotificationPreferences.fromJson(
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }

  Future<NotificationPreferences> updateNotificationPreferences({
    required bool emailEnabled,
    String? emailAddress,
    required bool ntfyEnabled,
  }) async {
    final headers = await _authHeaders();
    final body = {
      'email_enabled': emailEnabled,
      'email_address': emailAddress,
      'ntfy_enabled': ntfyEnabled,
    };
    final uri = Uri.parse('$baseUrl/v1/notifications/preferences');
    final response = await _httpClient.put(
      uri,
      headers: headers,
      body: jsonEncode(body),
    );
    _checkResponse(response);
    return NotificationPreferences.fromJson(
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }

  Future<List<DeviceToken>> listDeviceTokens() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/notifications/devices');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final body = _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
    final list = (body['devices'] as List<dynamic>?) ?? [];
    return list.map((e) => DeviceToken.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<DeviceToken> registerDeviceToken({
    required String token,
    String? deviceLabel,
  }) async {
    final headers = await _authHeaders();
    final body = <String, dynamic>{'token': token, 'token_type': 'ntfy'};
    if (deviceLabel != null) body['device_label'] = deviceLabel;
    final uri = Uri.parse('$baseUrl/v1/notifications/devices');
    final response = await _httpClient.post(
      uri,
      headers: headers,
      body: jsonEncode(body),
    );
    _checkResponse(response);
    return DeviceToken.fromJson(
      _unwrap(jsonDecode(response.body) as Map<String, dynamic>),
    );
  }

  Future<void> deleteDeviceToken(String tokenId) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/notifications/devices/$tokenId');
    final response = await _httpClient.delete(uri, headers: headers);
    _checkResponse(response);
  }

  Future<List<FeedItem>> getNotificationFeed({int limit = 20}) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/notifications/feed?limit=$limit');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final body = _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
    final list = (body['items'] as List<dynamic>?) ?? [];
    return list.map((e) => FeedItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ─── Memory (F-extend, B12) ───────────────────────────────────────────────

  Future<List<MemoryHit>> searchMemory(
    String query, {
    String bank = 'decisions',
    int limit = 10,
  }) async {
    final headers = await _authHeaders();
    final uri = Uri.parse(
      '$baseUrl/v1/memory/search?q=${Uri.encodeQueryComponent(query)}'
      '&bank=$bank&limit=$limit',
    );
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final body = _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
    final list = (body['hits'] as List<dynamic>?) ?? [];
    return list.map((e) => MemoryHit.fromJson(e as Map<String, dynamic>)).toList();
  }

  // ─── Analytics (B8 / F-extend) ────────────────────────────────────────────

  Future<Map<String, dynamic>> getAnalyticsConsensus() async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/analytics/consensus');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    return _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<Map<String, dynamic>> getAnalyticsVelocity({int days = 30}) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/analytics/velocity?days=$days');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    return _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
  }

  Future<List<dynamic>> getAnalyticsMembers({int limit = 20}) async {
    final headers = await _authHeaders();
    final uri = Uri.parse('$baseUrl/v1/analytics/members?limit=$limit');
    final response = await _httpClient.get(uri, headers: headers);
    _checkResponse(response);
    final body = _unwrap(jsonDecode(response.body) as Map<String, dynamic>);
    return (body['data'] as List<dynamic>?) ?? [];
  }
}
