package com.jhaa2k.vooc;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.SystemClock;

/**
 * Native Android media session. Android 11+ surfaces this in the system media
 * player (Quick Settings); older supported Android versions use it for lock
 * screen transport controls. The Python listener keeps transport actions in
 * sync with Vooc's existing player and playlist.
 */
public final class MediaSessionController {
    public interface Listener {
        void onPlay();
        void onPause();
        void onNext();
        void onPrevious();
        void onSeek(long positionMs);
    }

    private final MediaSession session;
    private final Listener listener;
    private volatile boolean released;

    public MediaSessionController(Activity activity, Listener listener) {
        this.listener = listener;
        session = new MediaSession(activity, "Vooc");
        session.setFlags(MediaSession.FLAG_HANDLES_MEDIA_BUTTONS
                | MediaSession.FLAG_HANDLES_TRANSPORT_CONTROLS);
        session.setCallback(new MediaSession.Callback() {
            @Override public void onPlay() {
                if (!released && MediaSessionController.this.listener != null)
                    MediaSessionController.this.listener.onPlay();
            }
            @Override public void onPause() {
                if (!released && MediaSessionController.this.listener != null)
                    MediaSessionController.this.listener.onPause();
            }
            @Override public void onSkipToNext() {
                if (!released && MediaSessionController.this.listener != null)
                    MediaSessionController.this.listener.onNext();
            }
            @Override public void onSkipToPrevious() {
                if (!released && MediaSessionController.this.listener != null)
                    MediaSessionController.this.listener.onPrevious();
            }
            @Override public void onSeekTo(long positionMs) {
                if (!released && MediaSessionController.this.listener != null)
                    MediaSessionController.this.listener.onSeek(positionMs);
            }
        });
    }

    public void update(String title, String artist, String album, String artPath,
                       long positionMs, long durationMs, boolean playing, boolean active) {
        if (released) return;
        try {
            MediaMetadata.Builder metadata = new MediaMetadata.Builder()
                    .putString(MediaMetadata.METADATA_KEY_TITLE, safe(title, "Unknown track"))
                    .putString(MediaMetadata.METADATA_KEY_ARTIST, safe(artist, "Vooc"))
                    .putString(MediaMetadata.METADATA_KEY_ALBUM, safe(album, ""))
                    .putLong(MediaMetadata.METADATA_KEY_DURATION, Math.max(0L, durationMs));
            if (artPath != null && artPath.length() > 0) {
                Bitmap art = BitmapFactory.decodeFile(artPath);
                if (art != null) {
                    metadata.putBitmap(MediaMetadata.METADATA_KEY_ALBUM_ART, art);
                    metadata.putBitmap(MediaMetadata.METADATA_KEY_ART, art);
                }
            }
            session.setMetadata(metadata.build());

            long actions = PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                    | PlaybackState.ACTION_PLAY_PAUSE | PlaybackState.ACTION_SKIP_TO_NEXT
                    | PlaybackState.ACTION_SKIP_TO_PREVIOUS | PlaybackState.ACTION_SEEK_TO;
            PlaybackState state = new PlaybackState.Builder()
                    .setActions(actions)
                    .setState(playing ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED,
                            Math.max(0L, positionMs),
                            playing ? 1.0f : 0.0f,
                            SystemClock.elapsedRealtime())
                    .build();
            session.setPlaybackState(state);
            session.setActive(active);
        } catch (Throwable ignored) {
            // Media controls must never interrupt local playback.
        }
    }

    public void release() {
        if (released) return;
        released = true;
        try { session.setActive(false); } catch (Exception ignored) { }
        try { session.release(); } catch (Exception ignored) { }
    }

    private static String safe(String value, String fallback) {
        return value == null || value.length() == 0 ? fallback : value;
    }
}
