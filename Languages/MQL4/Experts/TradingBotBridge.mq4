#property strict
#property version   "1.00"
#property description "Token-authenticated Trading Bot bridge for MetaTrader 4"

input string BridgeBaseUrl = "http://127.0.0.1:8765";
input string BridgeToken = "";
input string TerminalId = "mt4-terminal";
input int PollIntervalSeconds = 1;
input int RequestTimeoutMs = 5000;
input bool EnableLiveOrders = false;

string g_base_url = "";
string g_bridge_token = "";
string g_terminal_id = "";
bool g_busy = false;
string g_receipt_file = "";

string Trim(string value)
{
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}

string Lower(string value)
{
   StringToLower(value);
   return value;
}

string JsonEscape(string value)
{
   string output = "";
   for(int index = 0; index < StringLen(value); index++)
   {
      ushort code = StringGetCharacter(value, index);
      if(code == 34)
         output += "\\\"";
      else if(code == 92)
         output += "\\\\";
      else if(code == 8)
         output += "\\b";
      else if(code == 9)
         output += "\\t";
      else if(code == 10)
         output += "\\n";
      else if(code == 12)
         output += "\\f";
      else if(code == 13)
         output += "\\r";
      else if(code < 32)
         output += "?";
      else
         output += ShortToString(code);
   }
   return output;
}

string JsonString(string value)
{
   return "\"" + JsonEscape(value) + "\"";
}

bool IsUnreserved(uchar value)
{
   return (value >= 'A' && value <= 'Z')
      || (value >= 'a' && value <= 'z')
      || (value >= '0' && value <= '9')
      || value == '-' || value == '_' || value == '.' || value == '~';
}

string UrlEncode(string value)
{
   uchar bytes[];
   int size = StringToCharArray(value, bytes, 0, WHOLE_ARRAY, CP_UTF8);
   string output = "";
   for(int index = 0; index < size - 1; index++)
   {
      uchar current = bytes[index];
      if(IsUnreserved(current))
         output += CharToString(current);
      else
         output += StringFormat("%%%02X", current);
   }
   return output;
}

int HexValue(ushort value)
{
   if(value >= '0' && value <= '9')
      return value - '0';
   if(value >= 'A' && value <= 'F')
      return value - 'A' + 10;
   if(value >= 'a' && value <= 'f')
      return value - 'a' + 10;
   return -1;
}

string UrlDecode(string value)
{
   uchar output_bytes[];
   int output_size = 0;
   for(int index = 0; index < StringLen(value); index++)
   {
      ushort current = StringGetCharacter(value, index);
      if(current == '+')
      {
         ArrayResize(output_bytes, output_size + 1);
         output_bytes[output_size++] = 32;
         continue;
      }
      if(current == '%' && index + 2 < StringLen(value))
      {
         int high = HexValue(StringGetCharacter(value, index + 1));
         int low = HexValue(StringGetCharacter(value, index + 2));
         if(high >= 0 && low >= 0)
         {
            ArrayResize(output_bytes, output_size + 1);
            output_bytes[output_size++] = (uchar)(high * 16 + low);
            index += 2;
            continue;
         }
      }
      uchar encoded[];
      int encoded_size = StringToCharArray(
         ShortToString(current), encoded, 0, WHOLE_ARRAY, CP_UTF8);
      int encoded_content_size = encoded_size > 0 ? encoded_size - 1 : 0;
      ArrayResize(output_bytes, output_size + encoded_content_size);
      for(int encoded_index = 0; encoded_index < encoded_content_size; encoded_index++)
         output_bytes[output_size++] = encoded[encoded_index];
   }
   return CharArrayToString(output_bytes, 0, output_size, CP_UTF8);
}

bool IsSafeTerminalId(string value)
{
   string normalized = Trim(value);
   int length = StringLen(normalized);
   if(length < 1 || length > 64)
      return false;
   for(int index = 0; index < length; index++)
   {
      ushort code = StringGetCharacter(normalized, index);
      bool is_upper = code >= 'A' && code <= 'Z';
      bool is_lower = code >= 'a' && code <= 'z';
      bool is_digit = code >= '0' && code <= '9';
      if(!is_upper && !is_lower && !is_digit && code != '.' && code != '_' && code != '-')
         return false;
   }
   return true;
}

bool IsSafeBridgeToken(string value)
{
   string normalized = Trim(value);
   int length = StringLen(normalized);
   if(length < 16 || length > 512)
      return false;
   for(int index = 0; index < length; index++)
   {
      ushort code = StringGetCharacter(normalized, index);
      if(code < 32 || code == 127)
         return false;
   }
   return true;
}

bool IsDecimal(string value)
{
   int length = StringLen(value);
   if(length < 1)
      return false;
   for(int index = 0; index < length; index++)
   {
      ushort code = StringGetCharacter(value, index);
      if(code < '0' || code > '9')
         return false;
   }
   return true;
}

bool ParseBridgeAuthority(string authority, string &host)
{
   host = "";
   if(StringLen(authority) == 0
      || StringFind(authority, "@") >= 0
      || StringFind(authority, "?") >= 0
      || StringFind(authority, "#") >= 0
      || StringFind(authority, "\\") >= 0)
      return false;

   string port = "";
   bool port_specified = false;
   if(StringSubstr(authority, 0, 1) == "[")
   {
      int close_bracket = StringFind(authority, "]");
      if(close_bracket <= 1)
         return false;
      host = StringSubstr(authority, 0, close_bracket + 1);
      string suffix = StringSubstr(authority, close_bracket + 1);
      if(StringLen(suffix) > 0)
      {
         if(StringSubstr(suffix, 0, 1) != ":")
            return false;
         port_specified = true;
         port = StringSubstr(suffix, 1);
      }
   }
   else
   {
      if(StringFind(authority, "[") >= 0 || StringFind(authority, "]") >= 0)
         return false;
      int colon = StringFind(authority, ":");
      if(colon >= 0)
      {
         if(StringFind(authority, ":", colon + 1) >= 0)
            return false;
         port_specified = true;
         host = StringSubstr(authority, 0, colon);
         port = StringSubstr(authority, colon + 1);
      }
      else
         host = authority;
   }

   if(StringLen(host) == 0 || (port_specified && StringLen(port) == 0))
      return false;
   if(StringLen(port) > 0)
   {
      if(!IsDecimal(port))
         return false;
      int numeric_port = (int)StringToInteger(port);
      if(numeric_port < 1 || numeric_port > 65535)
         return false;
   }
   return true;
}

bool IsSafeBridgeBaseUrl(string value)
{
   string normalized = Lower(Trim(value));
   int length = StringLen(normalized);
   if(length == 0)
      return false;
   for(int index = 0; index < length; index++)
   {
      ushort code = StringGetCharacter(normalized, index);
      if(code < 33 || code == 127)
         return false;
   }
   if(StringFind(normalized, "@") >= 0
      || StringFind(normalized, "?") >= 0
      || StringFind(normalized, "#") >= 0
      || StringFind(normalized, "\\") >= 0)
      return false;

   bool secure = false;
   int scheme_length = 0;
   if(StringFind(normalized, "http://") == 0)
      scheme_length = 7;
   else if(StringFind(normalized, "https://") == 0)
   {
      scheme_length = 8;
      secure = true;
   }
   else
      return false;

   string authority_and_path = StringSubstr(normalized, scheme_length);
   int path_start = StringFind(authority_and_path, "/");
   string authority = path_start >= 0
      ? StringSubstr(authority_and_path, 0, path_start)
      : authority_and_path;
   string host = "";
   if(!ParseBridgeAuthority(authority, host))
      return false;
   if(secure)
      return true;
   return host == "localhost" || host == "127.0.0.1" || host == "[::1]";
}

string FormValue(string body, string requested_key)
{
   string pairs[];
   int count = StringSplit(body, '&', pairs);
   for(int index = 0; index < count; index++)
   {
      int separator = StringFind(pairs[index], "=");
      string key = separator < 0 ? pairs[index] : StringSubstr(pairs[index], 0, separator);
      if(UrlDecode(key) != requested_key)
         continue;
      string value = separator < 0 ? "" : StringSubstr(pairs[index], separator + 1);
      return UrlDecode(value);
   }
   return "";
}

bool HttpRequest(
   string method,
   string url,
   string body,
   int &status_code,
   string &response_body,
   int &transport_error)
{
   char request_data[];
   if(StringLen(body) > 0)
   {
      uchar request_utf8[];
      int request_size = StringToCharArray(body, request_utf8, 0, WHOLE_ARRAY, CP_UTF8);
      int data_size = request_size > 0 ? request_size - 1 : 0;
      ArrayResize(request_data, data_size);
      for(int request_index = 0; request_index < data_size; request_index++)
         request_data[request_index] = (char)request_utf8[request_index];
   }
   else
      ArrayResize(request_data, 0);

   char response_data[];
   string response_headers = "";
   string headers = "X-MT4-Bridge-Token: " + g_bridge_token + "\r\n"
      + "Accept: application/json, application/x-www-form-urlencoded\r\n"
      + "Content-Type: application/x-www-form-urlencoded\r\n";
   ResetLastError();
   status_code = WebRequest(
      method,
      url,
      headers,
      RequestTimeoutMs,
      request_data,
      response_data,
      response_headers);
   transport_error = GetLastError();
   uchar response_utf8[];
   ArrayResize(response_utf8, ArraySize(response_data));
   for(int response_index = 0; response_index < ArraySize(response_data); response_index++)
      response_utf8[response_index] = (uchar)response_data[response_index];
   response_body = CharArrayToString(response_utf8, 0, -1, CP_UTF8);
   return status_code >= 0;
}

bool SaveReceipt(
   string command_id,
   string status,
   int error_code,
   string error_message,
   string payload_json)
{
   int handle = FileOpen(
      g_receipt_file,
      FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI,
      '\t',
      CP_UTF8);
   if(handle == INVALID_HANDLE)
      return false;
   FileWrite(
      handle,
      command_id,
      status,
      IntegerToString(error_code),
      UrlEncode(error_message),
      UrlEncode(payload_json));
   FileFlush(handle);
   FileClose(handle);
   return true;
}

bool LoadReceipt(
   string command_id,
   string &status,
   int &error_code,
   string &error_message,
   string &payload_json)
{
   int handle = FileOpen(
      g_receipt_file,
      FILE_READ | FILE_CSV | FILE_COMMON | FILE_ANSI,
      '\t',
      CP_UTF8);
   if(handle == INVALID_HANDLE)
      return false;
   string stored_id = FileReadString(handle);
   string stored_status = FileReadString(handle);
   string stored_error = FileReadString(handle);
   string stored_message = FileReadString(handle);
   string stored_payload = FileReadString(handle);
   FileClose(handle);
   if(stored_id != command_id)
      return false;
   status = stored_status;
   error_code = (int)StringToInteger(stored_error);
   error_message = UrlDecode(stored_message);
   payload_json = UrlDecode(stored_payload);
   return true;
}

string AccountSnapshotJson()
{
   return "{"
      + "\"account_number\":" + IntegerToString(AccountNumber()) + ","
      + "\"company\":" + JsonString(AccountCompany()) + ","
      + "\"server\":" + JsonString(AccountServer()) + ","
      + "\"currency\":" + JsonString(AccountCurrency()) + ","
      + "\"name\":" + JsonString(AccountName()) + ","
      + "\"balance\":" + DoubleToString(AccountBalance(), 8) + ","
      + "\"credit\":" + DoubleToString(AccountCredit(), 8) + ","
      + "\"equity\":" + DoubleToString(AccountEquity(), 8) + ","
      + "\"free_margin\":" + DoubleToString(AccountFreeMargin(), 8) + ","
      + "\"margin\":" + DoubleToString(AccountMargin(), 8) + ","
      + "\"profit\":" + DoubleToString(AccountProfit(), 8) + ","
      + "\"trade_allowed\":" + (IsTradeAllowed() ? "true" : "false")
      + "}";
}

string MarketSnapshotJson(string symbol)
{
   SymbolSelect(symbol, true);
   int digits = (int)MarketInfo(symbol, MODE_DIGITS);
   return "{"
      + "\"symbol\":" + JsonString(symbol) + ","
      + "\"bid\":" + DoubleToString(MarketInfo(symbol, MODE_BID), digits) + ","
      + "\"ask\":" + DoubleToString(MarketInfo(symbol, MODE_ASK), digits) + ","
      + "\"point\":" + DoubleToString(MarketInfo(symbol, MODE_POINT), digits) + ","
      + "\"digits\":" + IntegerToString(digits) + ","
      + "\"spread_points\":" + DoubleToString(MarketInfo(symbol, MODE_SPREAD), 2) + ","
      + "\"min_lot\":" + DoubleToString(MarketInfo(symbol, MODE_MINLOT), 8) + ","
      + "\"max_lot\":" + DoubleToString(MarketInfo(symbol, MODE_MAXLOT), 8) + ","
      + "\"lot_step\":" + DoubleToString(MarketInfo(symbol, MODE_LOTSTEP), 8) + ","
      + "\"stop_level_points\":" + DoubleToString(MarketInfo(symbol, MODE_STOPLEVEL), 2) + ","
      + "\"quote_time\":" + IntegerToString((int)MarketInfo(symbol, MODE_TIME))
      + "}";
}

string OrderTypeName(int order_type)
{
   if(order_type == OP_BUY) return "buy";
   if(order_type == OP_SELL) return "sell";
   if(order_type == OP_BUYLIMIT) return "buy_limit";
   if(order_type == OP_SELLLIMIT) return "sell_limit";
   if(order_type == OP_BUYSTOP) return "buy_stop";
   if(order_type == OP_SELLSTOP) return "sell_stop";
   return "unknown";
}

string SelectedOrderJson()
{
   return "{"
      + "\"ticket\":" + IntegerToString(OrderTicket()) + ","
      + "\"symbol\":" + JsonString(OrderSymbol()) + ","
      + "\"type\":" + JsonString(OrderTypeName(OrderType())) + ","
      + "\"volume\":" + DoubleToString(OrderLots(), 8) + ","
      + "\"open_price\":" + DoubleToString(OrderOpenPrice(), 10) + ","
      + "\"stop_loss\":" + DoubleToString(OrderStopLoss(), 10) + ","
      + "\"take_profit\":" + DoubleToString(OrderTakeProfit(), 10) + ","
      + "\"profit\":" + DoubleToString(OrderProfit(), 8) + ","
      + "\"swap\":" + DoubleToString(OrderSwap(), 8) + ","
      + "\"commission\":" + DoubleToString(OrderCommission(), 8) + ","
      + "\"magic\":" + IntegerToString(OrderMagicNumber()) + ","
      + "\"comment\":" + JsonString(OrderComment()) + ","
      + "\"open_time\":" + IntegerToString((int)OrderOpenTime())
      + "}";
}

string OpenOrdersJson(bool positions_only, string symbol_filter)
{
   string items = "";
   int matched = 0;
   int total = OrdersTotal();
   for(int position = 0; position < total; position++)
   {
      if(!OrderSelect(position, SELECT_BY_POS, MODE_TRADES))
         continue;
      bool is_position = OrderType() == OP_BUY || OrderType() == OP_SELL;
      if(is_position != positions_only)
         continue;
      if(StringLen(symbol_filter) > 0 && OrderSymbol() != symbol_filter)
         continue;
      if(matched > 0)
         items += ",";
      items += SelectedOrderJson();
      matched++;
   }
   string key = positions_only ? "positions" : "orders";
   return "{\"" + key + "\":[" + items + "],\"count\":" + IntegerToString(matched) + "}";
}

bool ValidateVolume(string symbol, double volume, int &error_code, string &error_message)
{
   double minimum = MarketInfo(symbol, MODE_MINLOT);
   double maximum = MarketInfo(symbol, MODE_MAXLOT);
   double step = MarketInfo(symbol, MODE_LOTSTEP);
   if(minimum <= 0 || maximum <= 0 || step <= 0)
   {
      error_code = 9101;
      error_message = "broker did not expose valid lot constraints";
      return false;
   }
   if(volume < minimum - 1e-9 || volume > maximum + 1e-9)
   {
      error_code = 9102;
      error_message = "volume is outside broker lot limits";
      return false;
   }
   double steps = volume / step;
   if(MathAbs(steps - MathRound(steps)) > 1e-7)
   {
      error_code = 9103;
      error_message = "volume does not align with broker lot step";
      return false;
   }
   return true;
}

bool ExecuteMarketOrder(
   string command,
   string &payload_json,
   int &error_code,
   string &error_message)
{
   string symbol = Trim(FormValue(command, "symbol"));
   string side = Lower(Trim(FormValue(command, "side")));
   double volume = StringToDouble(FormValue(command, "volume"));
   double stop_loss = StringToDouble(FormValue(command, "stop_loss"));
   double take_profit = StringToDouble(FormValue(command, "take_profit"));
   int deviation = (int)StringToInteger(FormValue(command, "deviation"));
   int magic = (int)StringToInteger(FormValue(command, "magic"));
   string comment = FormValue(command, "comment");
   if(StringLen(symbol) == 0 || (side != "buy" && side != "sell"))
   {
      error_code = 9110;
      error_message = "invalid market order symbol or side";
      return false;
   }
   if(!SymbolSelect(symbol, true))
   {
      error_code = GetLastError();
      error_message = "could not select symbol";
      return false;
   }
   if(!ValidateVolume(symbol, volume, error_code, error_message))
      return false;
   if(!IsTradeAllowed())
   {
      error_code = 9111;
      error_message = "MT4 terminal does not currently allow trading";
      return false;
   }
   RefreshRates();
   int digits = (int)MarketInfo(symbol, MODE_DIGITS);
   int operation = side == "buy" ? OP_BUY : OP_SELL;
   double price = side == "buy" ? MarketInfo(symbol, MODE_ASK) : MarketInfo(symbol, MODE_BID);
   price = NormalizeDouble(price, digits);
   stop_loss = stop_loss > 0 ? NormalizeDouble(stop_loss, digits) : 0;
   take_profit = take_profit > 0 ? NormalizeDouble(take_profit, digits) : 0;
   ResetLastError();
   int ticket = OrderSend(
      symbol,
      operation,
      volume,
      price,
      deviation,
      stop_loss,
      take_profit,
      comment,
      magic,
      0,
      clrNONE);
   if(ticket < 0)
   {
      error_code = GetLastError();
      error_message = "OrderSend failed";
      return false;
   }
   payload_json = "{\"ticket\":" + IntegerToString(ticket)
      + ",\"symbol\":" + JsonString(symbol)
      + ",\"side\":" + JsonString(side)
      + ",\"volume\":" + DoubleToString(volume, 8) + "}";
   return true;
}

bool ExecuteCancelOrder(
   string command,
   string &payload_json,
   int &error_code,
   string &error_message)
{
   int ticket = (int)StringToInteger(FormValue(command, "ticket"));
   ResetLastError();
   if(ticket <= 0 || !OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      error_code = GetLastError();
      error_message = "pending order ticket was not found";
      return false;
   }
   int order_type = OrderType();
   if(order_type == OP_BUY || order_type == OP_SELL)
   {
      error_code = 9120;
      error_message = "market positions must use close_position";
      return false;
   }
   if(!OrderDelete(ticket, clrNONE))
   {
      error_code = GetLastError();
      error_message = "OrderDelete failed";
      return false;
   }
   payload_json = "{\"ticket\":" + IntegerToString(ticket) + ",\"cancelled\":true}";
   return true;
}

bool ExecuteClosePosition(
   string command,
   string &payload_json,
   int &error_code,
   string &error_message)
{
   int ticket = (int)StringToInteger(FormValue(command, "ticket"));
   double requested_volume = StringToDouble(FormValue(command, "volume"));
   int deviation = (int)StringToInteger(FormValue(command, "deviation"));
   ResetLastError();
   if(ticket <= 0 || !OrderSelect(ticket, SELECT_BY_TICKET, MODE_TRADES))
   {
      error_code = GetLastError();
      error_message = "position ticket was not found";
      return false;
   }
   int order_type = OrderType();
   if(order_type != OP_BUY && order_type != OP_SELL)
   {
      error_code = 9130;
      error_message = "pending orders must use cancel_order";
      return false;
   }
   string symbol = OrderSymbol();
   double volume = requested_volume > 0 ? requested_volume : OrderLots();
   if(volume > OrderLots() + 1e-9 || !ValidateVolume(symbol, volume, error_code, error_message))
   {
      if(error_code == 0)
      {
         error_code = 9131;
         error_message = "close volume exceeds open position volume";
      }
      return false;
   }
   RefreshRates();
   int digits = (int)MarketInfo(symbol, MODE_DIGITS);
   double price = order_type == OP_BUY
      ? MarketInfo(symbol, MODE_BID)
      : MarketInfo(symbol, MODE_ASK);
   price = NormalizeDouble(price, digits);
   if(!OrderClose(ticket, volume, price, deviation, clrNONE))
   {
      error_code = GetLastError();
      error_message = "OrderClose failed";
      return false;
   }
   payload_json = "{\"ticket\":" + IntegerToString(ticket)
      + ",\"closed\":true,\"volume\":" + DoubleToString(volume, 8) + "}";
   return true;
}

bool IsMutation(string operation)
{
   return operation == "market_order"
      || operation == "cancel_order"
      || operation == "close_position";
}

void ExecuteCommand(
   string command,
   string &status,
   string &payload_json,
   int &error_code,
   string &error_message)
{
   string operation = Lower(Trim(FormValue(command, "operation")));
   status = "completed";
   payload_json = "null";
   error_code = 0;
   error_message = "";

   if(IsMutation(operation) && !EnableLiveOrders)
   {
      status = "failed";
      error_code = 9000;
      error_message = "EnableLiveOrders is false in the MT4 Expert Advisor";
      return;
   }
   bool success = true;
   if(operation == "account_snapshot")
      payload_json = AccountSnapshotJson();
   else if(operation == "market_snapshot")
      payload_json = MarketSnapshotJson(Trim(FormValue(command, "symbol")));
   else if(operation == "open_positions_snapshot")
      payload_json = OpenOrdersJson(true, Trim(FormValue(command, "symbol")));
   else if(operation == "open_orders_snapshot")
      payload_json = OpenOrdersJson(false, Trim(FormValue(command, "symbol")));
   else if(operation == "market_order")
      success = ExecuteMarketOrder(command, payload_json, error_code, error_message);
   else if(operation == "cancel_order")
      success = ExecuteCancelOrder(command, payload_json, error_code, error_message);
   else if(operation == "close_position")
      success = ExecuteClosePosition(command, payload_json, error_code, error_message);
   else
   {
      success = false;
      error_code = 9002;
      error_message = "unsupported bridge operation";
   }
   if(!success)
   {
      status = "failed";
      payload_json = "null";
   }
}

bool PostResult(
   string command_id,
   string status,
   string payload_json,
   int error_code,
   string error_message)
{
   string body = "command_id=" + UrlEncode(command_id)
      + "&status=" + UrlEncode(status)
      + "&error_code=" + IntegerToString(error_code)
      + "&error_message=" + UrlEncode(error_message)
      + "&payload_json=" + UrlEncode(payload_json);
   int status_code = 0;
   int transport_error = 0;
   string response = "";
   string url = g_base_url + "/v1/agents/" + UrlEncode(g_terminal_id) + "/results";
   if(!HttpRequest("POST", url, body, status_code, response, transport_error))
   {
      Print("TradingBotBridge result transport failed: ", transport_error);
      return false;
   }
   if(status_code != 200)
   {
      Print("TradingBotBridge result HTTP status: ", status_code);
      return false;
   }
   return true;
}

void PollBridge()
{
   int status_code = 0;
   int transport_error = 0;
   string response = "";
   string url = g_base_url + "/v1/agents/" + UrlEncode(g_terminal_id) + "/next";
   if(!HttpRequest("GET", url, "", status_code, response, transport_error))
   {
      Print("TradingBotBridge poll transport failed: ", transport_error);
      return;
   }
   if(status_code == 204)
      return;
   if(status_code != 200)
   {
      Print("TradingBotBridge poll HTTP status: ", status_code);
      return;
   }
   if(FormValue(response, "protocol") != "1")
   {
      Print("TradingBotBridge rejected an incompatible protocol response");
      return;
   }
   string command_id = Lower(Trim(FormValue(response, "command_id")));
   if(StringLen(command_id) != 32)
   {
      Print("TradingBotBridge received an invalid command id");
      return;
   }

   string status = "";
   string payload_json = "";
   int error_code = 0;
   string error_message = "";
   if(LoadReceipt(command_id, status, error_code, error_message, payload_json))
   {
      PostResult(command_id, status, payload_json, error_code, error_message);
      return;
   }

   string operation = Lower(Trim(FormValue(response, "operation")));
   if(IsMutation(operation))
   {
      string guard_message = "mutation outcome is ambiguous after terminal interruption; reconcile before retry";
      if(!SaveReceipt(command_id, "failed", 9001, guard_message, "null"))
      {
         PostResult(command_id, "failed", "null", 9003, "could not persist mutation receipt");
         return;
      }
   }

   ExecuteCommand(response, status, payload_json, error_code, error_message);
   if(!SaveReceipt(command_id, status, error_code, error_message, payload_json))
   {
      Print("TradingBotBridge could not persist the completed receipt");
      return;
   }
   PostResult(command_id, status, payload_json, error_code, error_message);
}

int OnInit()
{
   g_base_url = Trim(BridgeBaseUrl);
   while(StringLen(g_base_url) > 0 && StringSubstr(g_base_url, StringLen(g_base_url) - 1) == "/")
      g_base_url = StringSubstr(g_base_url, 0, StringLen(g_base_url) - 1);
   g_bridge_token = Trim(BridgeToken);
   g_terminal_id = Trim(TerminalId);
   if(!IsSafeBridgeBaseUrl(g_base_url)
      || !IsSafeBridgeToken(g_bridge_token)
      || !IsSafeTerminalId(g_terminal_id))
   {
      Print("TradingBotBridge requires loopback HTTP or HTTPS BridgeBaseUrl, a 16-512 character BridgeToken, and a safe TerminalId");
      return INIT_PARAMETERS_INCORRECT;
   }
   if(PollIntervalSeconds < 1 || PollIntervalSeconds > 3600
      || RequestTimeoutMs < 100 || RequestTimeoutMs > 120000)
   {
      Print("TradingBotBridge timing inputs must be within the supported bounds");
      return INIT_PARAMETERS_INCORRECT;
   }
   g_receipt_file = "TradingBotBridge_" + g_terminal_id + ".receipt.tsv";
   EventSetTimer(PollIntervalSeconds);
   Print("TradingBotBridge initialized for terminal ", g_terminal_id,
      ". Add the bridge URL to Tools > Options > Expert Advisors > Allow WebRequest.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   if(g_busy)
      return;
   g_busy = true;
   PollBridge();
   g_busy = false;
}
