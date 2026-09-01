<?php
/**
 * Plugin Name: iAAWG – Yoast SEO REST Bridge (OPSIONAL)
 * Description: Mendaftarkan meta field Yoast SEO (_yoast_wpseo_focuskw,
 *              _yoast_wpseo_metadesc, _yoast_wpseo_title) supaya bisa ditulis
 *              lewat WordPress REST API (wp/v2/posts), untuk versi Yoast SEO
 *              yang belum mendaftarkan field ini sendiri.
 * Version:     1.0.0
 * Author:      iAAWG / iLogo Infralogy Indonesia
 *
 * STATUS: TIDAK WAJIB. Diverifikasi (2026-09) bahwa Yoast SEO versi terbaru
 * sudah otomatis mendaftarkan field-field ini untuk REST API sendiri — hasil
 * test langsung menunjukkan focus keyphrase & meta description dari Blog
 * Autopost sudah tersimpan dengan benar TANPA plugin ini aktif. Simpan file
 * ini sebagai fallback saja, untuk jaga-jaga kalau ada instalasi WordPress /
 * versi Yoast lain di mana field ini ternyata tidak ter-registrasi — aman
 * diaktifkan kapan pun (idempotent, tidak bentrok kalau Yoast sudah
 * mendaftarkan field yang sama).
 *
 * INSTALLATION (kalau suatu saat dibutuhkan):
 *   1. Buat folder: wp-content/plugins/iaawg-yoast-rest-bridge/
 *   2. Letakkan file ini di dalamnya.
 *   3. Aktifkan dari WordPress Admin → Plugins.
 *
 * Aman diaktifkan meskipun Yoast SEO tidak terpasang — plugin ini hanya
 * mendaftarkan meta key, tidak bergantung pada class/fungsi Yoast apa pun.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

add_action( 'init', function () {

    $fields = [
        '_yoast_wpseo_focuskw'  => 'Yoast SEO focus keyphrase.',
        '_yoast_wpseo_metadesc' => 'Yoast SEO meta description.',
        '_yoast_wpseo_title'    => 'Yoast SEO title (override template default).',
    ];

    foreach ( $fields as $key => $description ) {
        register_post_meta( 'post', $key, [
            'show_in_rest'  => true,
            'single'        => true,
            'type'          => 'string',
            'description'   => $description,
            'auth_callback' => function () {
                return current_user_can( 'edit_posts' );
            },
        ] );
    }

}, 20 );
