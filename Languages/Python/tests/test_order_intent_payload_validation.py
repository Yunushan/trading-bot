"""Pure full-ledger validation keeps global ownership and recovery evidence intact."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import order_intent_runtime as ledger
from app.integrations.exchanges.binance.orders.spot_allocation_generation_runtime import canonical_spot_buy_metadata
from app.integrations.exchanges.binance.orders.spot_fill_recovery_runtime import summarize_primary_spot_buy
from app.settings.live_safety import LiveTradingSafetyError
from tools import benchmark_spot_intent_history as capacity
from tools import spot_intent_capacity_profiles as profiles


def market_payload():
    return capacity.synthetic_payload(6, 2)


def opo_payload():
    payload = market_payload()
    payload['intents'], _ = profiles.synthetic_opo_records(
        6, original_stops=1, residual_stops=1, attempt_depth=2, residual_depth=2,
    )
    return payload


def primary_payload():
    payload = market_payload()
    client_id = 'pure-primary-buy'
    order = {
        'symbol': 'BTCUSDT', 'clientOrderId': client_id, 'orderId': 913, 'side': 'BUY', 'type': 'MARKET',
        'status': 'FILLED', 'origQty': '0.1', 'executedQty': '0.1', 'cummulativeQuoteQty': '10',
        'transactTime': 1_750_000_000_000,
        'fills': [{'tradeId': 1913, 'price': '100', 'qty': '0.1', 'commission': '0.00004',
                   'commissionAsset': 'BTC'}],
    }
    fill = summarize_primary_spot_buy(order, symbol='BTCUSDT', client_order_id=client_id,
                                     base_asset='BTC', quote_asset='USDT')
    record = ledger._intent_record({'newClientOrderId': client_id, 'symbol': 'BTCUSDT', 'side': 'BUY',
                                   'type': 'MARKET', 'quantity': '0.1'}, market='spot', source='pure-validation-fixture')
    record.update(state='accepted', exchange_status='FILLED', exchange_order_id='913', executed_qty='0.1',
                  portfolio_qty=fill['net_qty'], primary_fill_signature=fill['signature'],
                  primary_fill_receipt=canonical_spot_buy_metadata(fill))
    record['desktop_entry_source'] = {
        'version': 1, 'allocation_path': str(Path(__file__).resolve().parent / 'never-read-allocations.json'),
        'mode': 'Live', 'snapshot_signature': 'a' * 64, 'absent': True, 'generation': 3,
        'target_key': ['BTCUSDT', 'L'], 'client_order_ids': [client_id],
    }
    payload['intents'] = {client_id: record}
    return payload


class OrderIntentPayloadValidationTests(unittest.TestCase):
    def test_complete_accepted_payloads_preserve_identity_and_have_no_storage_or_venue_access(self):
        legacy = {'format_version': 1, 'intents': deepcopy(market_payload()['intents'])}
        for name, payload, allow_legacy in (
            ('market', market_payload(), False), ('opo', opo_payload(), False),
            ('primary', primary_payload(), False), ('legacy', legacy, True),
        ):
            before = deepcopy(payload)
            with self.subTest(name=name), \
                 patch.object(Path, 'read_text', side_effect=AssertionError('Pure validation cannot read files')), \
                 patch.object(Path, 'read_bytes', side_effect=AssertionError('Pure validation cannot read files')), \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')), \
                 patch.object(socket, 'create_connection', side_effect=AssertionError('No network')):
                accepted = ledger.validate_order_intent_ledger(
                    payload, expected_binding=payload.get('binding'), allow_legacy=allow_legacy,
                )
                self.assertIs(payload, accepted)
                self.assertEqual(before, payload)

    def test_json_reader_delegates_to_the_complete_validator_with_existing_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ledger.json'
            for payload, allow_legacy in ((opo_payload(), False), ({'format_version': 1, 'intents': {}}, True)):
                with self.subTest(allow_legacy=allow_legacy):
                    path.write_text(json.dumps(payload))
                    with patch.object(ledger, 'validate_order_intent_ledger',
                                      wraps=ledger.validate_order_intent_ledger) as validate:
                        result = ledger._read_ledger(path, expected_binding=payload.get('binding'),
                                                     allow_legacy=allow_legacy)
                    self.assertEqual(payload, result)
                    validate.assert_called_once_with(payload, expected_binding=payload.get('binding'),
                                                     allow_legacy=allow_legacy)

    def test_duplicate_json_fields_remain_decoder_errors_before_payload_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'ledger.json'
            path.write_text('{"format_version":2,"intents":{},"intents":{}}')
            with patch.object(ledger, 'validate_order_intent_ledger',
                              wraps=ledger.validate_order_intent_ledger) as validate:
                with self.assertRaisesRegex(LiveTradingSafetyError, 'cannot be read'):
                    ledger._read_ledger(path)
            validate.assert_not_called()

    def test_cross_record_alias_conflict_is_rejected_even_when_each_full_record_is_valid(self):
        payload = opo_payload()
        residual = payload['intents']['syn-list-00000001']
        alias = residual['pending_observed_client_order_id']
        other = ledger._intent_record({'newClientOrderId': alias, 'symbol': 'BTCUSDT', 'side': 'BUY',
                                      'type': 'MARKET', 'quantity': '0.1'}, market='spot', source='other-intent')
        # Two individually valid complete ledgers do not prove combined ID ownership.
        for record in (residual, other):
            separate = {**deepcopy(payload), 'intents': {record['client_order_id']: deepcopy(record)}}
            self.assertIs(separate, ledger.validate_order_intent_ledger(separate))
        payload['intents'][alias] = other
        before = deepcopy(payload)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'alias conflicts with another durable Spot intent'):
            ledger.validate_order_intent_ledger(payload)
        self.assertEqual(before, payload)

    def test_current_and_archived_recovery_evidence_cannot_be_weakened_by_pure_access(self):
        for change in ('exit_archive', 'residual_archive', 'primary_status', 'primary_version', 'desktop_source'):
            with self.subTest(change=change):
                payload = primary_payload() if change.startswith('primary') or change == 'desktop_source' else opo_payload()
                if change == 'exit_archive':
                    payload['intents']['syn-list-00000000']['strategy_exit_history'][0][
                        'strategy_exit_request_signature'] = '0' * 64
                elif change == 'residual_archive':
                    payload['intents']['syn-list-00000001']['residual_stop_history'][0]['request_signature'] = '0' * 64
                else:
                    record = payload['intents']['pure-primary-buy']
                    if change == 'primary_status':
                        record['exchange_status'] = 'CANCELED'
                    elif change == 'primary_version':
                        record['primary_fill_receipt']['version'] = True
                    else:
                        record['desktop_entry_source']['client_order_ids'] = ['different-client']
                before = deepcopy(payload)
                with self.assertRaises(LiveTradingSafetyError):
                    ledger.validate_order_intent_ledger(payload)
                self.assertEqual(before, payload)

    def test_metadata_rotation_binding_and_legacy_error_order_are_preserved(self):
        payload = market_payload()
        payload['binding']['credential_fingerprint'] = 'c' * 64
        payload['credential_rotation_history'] = [
            {'previous_fingerprint': 'a' * 64, 'new_fingerprint': 'b' * 64,
             'rotated_at': capacity.FIXED_TIME, 'reconciliation_reference': 'first offline rotation'},
            {'previous_fingerprint': 'b' * 64, 'new_fingerprint': 'c' * 64,
             'rotated_at': capacity.FIXED_TIME, 'reconciliation_reference': 'second offline rotation'},
        ]
        self.assertIs(payload, ledger.validate_order_intent_ledger(payload, expected_binding=payload['binding']))
        discontinuous = deepcopy(payload)
        discontinuous['credential_rotation_history'][1]['previous_fingerprint'] = 'd' * 64
        with self.assertRaisesRegex(LiveTradingSafetyError, 'invalid credential rotation history'):
            ledger.validate_order_intent_ledger(discontinuous)
        with self.assertRaisesRegex(LiveTradingSafetyError, 'different credentials or environment'):
            ledger.validate_order_intent_ledger(payload, expected_binding={**payload['binding'], 'environment': 'testnet'})
        legacy = {'format_version': 1, 'intents': {}}
        with self.assertRaisesRegex(LiveTradingSafetyError, 'requires explicit migration'):
            ledger.validate_order_intent_ledger(legacy)
        legacy['intents']['bad'] = {'client_order_id': 'bad', 'state': 'invalid'}
        with self.assertRaisesRegex(LiveTradingSafetyError, 'invalid record'):
            ledger.validate_order_intent_ledger(legacy)

    def test_invalid_payload_shapes_and_record_metadata_fail_without_mutation(self):
        cases = [None, [], {}, MappingProxyType(market_payload())]
        for field, value in (('format_version', True), ('format_version', 3), ('intents', []),
                             ('store_id', 'not-a-store-id'), ('created_at', '2026-01-01'),
                             ('binding', {}), ('credential_rotation_history', {})):
            payload = market_payload()
            payload[field] = value
            cases.append(payload)
        for field, value in (('state', 'invalid'), ('client_order_id', 'other-client'),
                             ('requires_close_confirmation', 1), ('portfolio_reconciled', 1)):
            payload = market_payload()
            payload['intents']['synthetic-history-00000000'][field] = value
            cases.append(payload)
        for index, payload in enumerate(cases):
            with self.subTest(index=index):
                before = dict(payload) if isinstance(payload, MappingProxyType) else deepcopy(payload)
                with self.assertRaises(LiveTradingSafetyError):
                    ledger.validate_order_intent_ledger(payload)
                self.assertEqual(before, dict(payload) if isinstance(payload, MappingProxyType) else payload)


class OrderIntentSelectiveValidationHelperTests(unittest.TestCase):
    @staticmethod
    def outcome(operation):
        try:
            operation()
        except LiveTradingSafetyError as exc:
            return type(exc), str(exc)
        return None

    @staticmethod
    def ownership(intents):
        owners = {}
        for key, record in intents.items():
            for client_id in ledger.used_spot_client_order_ids({key: record}):
                owners.setdefault(client_id, set()).add(key)
        aliases = {key: record for key, record in intents.items()
                   if isinstance(record.get('pending_observed_client_order_id'), str)}
        return aliases, owners

    def test_header_validation_uses_real_metadata_without_record_placeholder(self):
        for name, payload, allow_legacy in (
            ('market', market_payload(), False), ('opo', opo_payload(), False),
            ('legacy', {'format_version': 1, 'intents': {}}, True),
        ):
            header = {key: deepcopy(value) for key, value in payload.items() if key != 'intents'}
            header['preserved-extension'] = {'opaque': True}
            before = deepcopy(header)
            with self.subTest(name=name), \
                 patch.object(Path, 'read_bytes', side_effect=AssertionError('No file read')), \
                 patch.object(socket.socket, 'connect', side_effect=AssertionError('No network')):
                self.assertIs(header, ledger.validate_order_intent_metadata(
                    header, expected_binding=header.get('binding'), allow_legacy=allow_legacy,
                ))
            self.assertEqual(before, header)
            self.assertNotIn('intents', header)

    def test_local_rules_match_complete_validation_for_financial_and_history_faults(self):
        for name, factory, key, mutations in (
            ('market', market_payload, 'synthetic-history-00000000',
             ({'state': 'invalid'}, {'client_order_id': 'other'}, {'requires_close_confirmation': 1},
              {'portfolio_reconciled': 1}, {'opaque-local-field': {'unchanged': True}})),
            ('primary', primary_payload, 'pure-primary-buy',
             ({'exchange_status': 'CANCELED'}, {'executed_qty': '0.09'}, {'portfolio_qty': '0.2'},
              {'primary_fill_signature': '0' * 64})),
            ('opo', opo_payload, 'syn-list-00000001',
             ({'residual_stop_order_id': True}, {'entry_reconciled': False},
              {'residual_stop_history': []}, {'pending_observed_client_order_id': 1})),
        ):
            for mutation in mutations:
                payload = factory()
                record = payload['intents'][key]
                record.update(mutation)
                before = deepcopy(payload)
                with self.subTest(name=name, mutation=mutation):
                    local = self.outcome(lambda: ledger.validate_order_intent_record(key, record))
                    complete = self.outcome(lambda: ledger.validate_order_intent_ledger(payload))
                    self.assertEqual(complete, local)
                    self.assertEqual(before, payload)
        for key, record in ((None, {}), ('bad', []), (' ', {}), (1, {})):
            with self.subTest(key=key, record=record):
                with self.assertRaisesRegex(LiveTradingSafetyError, 'invalid record'):
                    ledger.validate_order_intent_record(key, record)

    def test_metadata_rules_match_full_header_errors_and_legacy_behavior(self):
        for field, value in (('format_version', True), ('format_version', 3), ('store_id', None),
                             ('created_at', '2026-01-01'), ('binding', {}),
                             ('credential_rotation_history', {})):
            payload = market_payload()
            payload[field] = value
            header = {key: deepcopy(item) for key, item in payload.items() if key != 'intents'}
            before = deepcopy(header)
            with self.subTest(field=field):
                self.assertEqual(self.outcome(lambda: ledger.validate_order_intent_ledger(payload)),
                                 self.outcome(lambda: ledger.validate_order_intent_metadata(header)))
                self.assertEqual(before, header)
        for allow_legacy in (False, True):
            with self.subTest(allow_legacy=allow_legacy):
                self.assertEqual(self.outcome(lambda: ledger.validate_order_intent_ledger(
                    {'format_version': 1, 'intents': {}}, allow_legacy=allow_legacy)),
                    self.outcome(lambda: ledger.validate_order_intent_metadata(
                        {'format_version': 1}, allow_legacy=allow_legacy)))

    def test_complete_verified_ownership_index_detects_current_and_archived_collisions(self):
        for collision in ('none', 'current', 'archived'):
            payload = opo_payload()
            alias = payload['intents']['syn-list-00000001']['pending_observed_client_order_id']
            if collision == 'current':
                payload['intents'][alias] = ledger._intent_record(
                    {'newClientOrderId': alias, 'symbol': 'BTCUSDT', 'side': 'BUY',
                     'type': 'MARKET', 'quantity': '0.1'}, market='spot', source='ownership-fixture')
            elif collision == 'archived':
                original = profiles._active_original(9, 0)
                other = profiles._exit_attempt(original, 1, 3)
                other['strategy_exit_history'] = [
                    profiles.archive_spot_opo_no_effect_attempt(profiles._exit_attempt(original, 1, generation))
                    for generation in range(3)
                ]
                payload['intents'][other['client_order_id']] = other
                self.assertNotEqual(alias, other['strategy_exit_request']['cancelNewClientOrderId'])
                self.assertIn(alias, ledger.used_spot_client_order_ids({other['client_order_id']: other}))
            for key, record in payload['intents'].items():
                ledger.validate_order_intent_record(key, record)
            aliases, owners = self.ownership(payload['intents'])
            before = deepcopy((aliases, owners))
            with self.subTest(collision=collision):
                global_result = self.outcome(lambda: ledger.validate_order_intent_global_ownership(
                    aliases, owners=owners))
                self.assertEqual(self.outcome(lambda: ledger.validate_order_intent_ledger(payload)), global_result)
                if collision == 'none':
                    self.assertIsNone(global_result)
                else:
                    self.assertIn('another durable Spot intent', global_result[1])
                self.assertEqual(before, (aliases, owners))

    def test_full_validation_preserves_record_before_alias_before_metadata_errors(self):
        payload = opo_payload()
        residual = payload['intents']['syn-list-00000001']
        alias = residual['pending_observed_client_order_id']
        payload['intents'][alias] = ledger._intent_record(
            {'newClientOrderId': alias, 'symbol': 'BTCUSDT', 'side': 'BUY',
             'type': 'MARKET', 'quantity': '0.1'}, market='spot', source='error-order-fixture')
        payload['store_id'] = 'invalid-store'
        with self.assertRaisesRegex(LiveTradingSafetyError, 'another durable Spot intent'):
            ledger.validate_order_intent_ledger(payload)
        payload['intents']['syn-list-00000000']['state'] = 'invalid'
        with patch.object(ledger, 'validate_order_intent_global_ownership',
                          wraps=ledger.validate_order_intent_global_ownership) as ownership, \
             patch.object(ledger, 'validate_order_intent_metadata',
                          wraps=ledger.validate_order_intent_metadata) as metadata:
            with self.assertRaisesRegex(LiveTradingSafetyError, 'invalid record'):
                ledger.validate_order_intent_ledger(payload)
        ownership.assert_not_called()
        metadata.assert_not_called()
        payload['intents'] = []
        with patch.object(ledger, 'validate_order_intent_record',
                          wraps=ledger.validate_order_intent_record) as record:
            with self.assertRaisesRegex(LiveTradingSafetyError, 'ledger is malformed'):
                ledger.validate_order_intent_ledger(payload)
        record.assert_not_called()