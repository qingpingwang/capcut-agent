import test from 'node:test';
import assert from 'node:assert/strict';
import { ThreadStore, relativeTime, threadIndicator } from '../static/js/chat/thread-state.js';

test('running pulses, background completion stays lit, active completion is hidden', () => {
    assert.equal(threadIndicator({ running: true, unread: true }), 'running');
    assert.equal(threadIndicator({ running: true }, true), 'running');
    assert.equal(threadIndicator({ running: false, unread: true }), 'unread');
    assert.equal(threadIndicator({ unread: true }, true), '');
    assert.equal(threadIndicator({ unread: false }), '');
});

test('one minute clock updates relative time without refetching or rebuilding state', async () => {
    let tick, interval, requests = 0, cancelled = false;
    const store = new ThreadStore({
        schedule(callback, ms) { tick = callback; interval = ms; return 17; },
        unschedule(id) { assert.equal(id, 17); cancelled = true; },
        fetcher: async () => { requests++; return new Response(JSON.stringify({ threads: [{ thread_id: 'a', updated_at: '2026-09-22T00:00:00Z' }] })); },
    });
    const reasons = [];
    const unsubscribe = store.subscribe((threads, reason) => reasons.push(reason));
    await store.refresh();
    tick(); tick();
    assert.equal(interval, 60000);
    assert.equal(requests, 1);
    assert.deepEqual(reasons, ['data', 'data', 'clock', 'clock']);
    assert.equal(relativeTime(store.values()[0].updated_at, Date.parse('2026-09-22T00:02:00Z')), '2分钟前');
    assert.equal(relativeTime('invalid'), '');
    unsubscribe();
    store.destroy();
    assert.equal(cancelled, true);
});

test('late read receipt cannot replace a newer running state or revive a cleared reminder', async () => {
    const pending = [];
    const store = new ThreadStore({
        schedule: () => 1, unschedule: () => {},
        fetcher: url => new Promise(resolve => pending.push({ url, resolve })),
    });
    const respond = data => pending.shift().resolve(new Response(JSON.stringify(data)));
    const first = { thread_id: 'a', run_id: 'first', run_status: 'completed', running: false, unread: true };
    const second = { ...first, run_id: 'second', run_status: 'running', running: true, unread: false };
    let refresh = store.refresh();
    respond({ threads: [first] });
    await refresh;

    const staleRefresh = store.refresh();
    const read = store.markRead('a', 'first');
    pending[1].resolve(new Response(JSON.stringify({ run: { ...first, unread: false } })));
    pending.splice(1, 1);
    await read;
    respond({ threads: [first] }); // 发起于已读之前的列表响应迟到。
    await staleRefresh;
    assert.equal(store.values()[0].unread, false);

    const lateRead = store.markRead('a', 'first');
    refresh = store.refresh();
    pending[1].resolve(new Response(JSON.stringify({ threads: [second] })));
    pending.splice(1, 1);
    await refresh;
    respond({ run: { ...first, unread: false } });
    await lateRead;
    assert.equal(store.values()[0].run_id, 'second');
    assert.equal(store.values()[0].running, true);

    refresh = store.refresh();
    respond({ threads: [{ ...second, running: false, unread: true }] });
    await refresh;
    assert.equal(store.values()[0].unread, true, 'new completion still needs to be viewed');
    store.destroy();
});
