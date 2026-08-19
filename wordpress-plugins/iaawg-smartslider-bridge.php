<?php
/**
 * Plugin Name: iAAWG – Smart Slider 3 Bridge
 * Description: Membuka REST endpoint yang meneruskan file .ss3 (bundle export
 *              Smart Slider 3) ke Public PHP API resmi Nextend:
 *              \Nextend\SmartSlider3\PublicApi\Project::import().
 *              iAAWG cukup POST file .ss3 → dapat slider ID → inject shortcode.
 * Version:     1.0.0
 * Author:      iAAWG / iLogo Infralogy Indonesia
 *
 * INSTALLATION:
 *   1. Buat folder: wp-content/plugins/iaawg-smartslider-bridge/
 *   2. Letakkan file ini di dalamnya.
 *   3. Aktifkan dari WordPress Admin → Plugins.
 *
 * REQUIRES: Smart Slider 3 (free) sudah aktif terlebih dahulu.
 *
 * ENDPOINT: POST /wp-json/iaawg/v1/smartslider/import
 *   Body (multipart/form-data):
 *     ss3_file  (file, required)  — file .ss3 hasil export Smart Slider 3
 *   Auth: Basic Auth (Application Password), user harus punya cap 'manage_options'.
 *
 *   Response 200:
 *     { "success": true, "slider_id": <int>, "shortcode": "[smartslider3 slider=\"X\"]" }
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}


add_action( 'rest_api_init', function () {
    register_rest_route( 'iaawg/v1', '/smartslider/import', [
        'methods'             => 'POST',
        'callback'            => 'iaawg_ss3_import_project',
        'permission_callback' => function () {
            return current_user_can( 'manage_options' );
        },
    ] );
} );


function iaawg_ss3_import_project( WP_REST_Request $request ) {

    // ── 1. Verifikasi Smart Slider 3 aktif ────────────────────────────────────
    if ( ! class_exists( '\Nextend\SmartSlider3\PublicApi\Project' ) ) {
        return new WP_Error(
            'ss3_not_active',
            'Smart Slider 3 belum aktif. Aktifkan plugin terlebih dahulu.',
            [ 'status' => 503 ]
        );
    }

    // ── 2. Ambil file dari request ────────────────────────────────────────────
    $files = $request->get_file_params();
    if ( empty( $files['ss3_file'] ) || empty( $files['ss3_file']['tmp_name'] ) ) {
        return new WP_Error(
            'no_file',
            'Parameter multipart "ss3_file" tidak ditemukan.',
            [ 'status' => 400 ]
        );
    }

    $tmp_path = $files['ss3_file']['tmp_name'];
    if ( ! is_readable( $tmp_path ) ) {
        return new WP_Error(
            'unreadable',
            'File .ss3 upload tidak dapat dibaca dari server.',
            [ 'status' => 400 ]
        );
    }

    // ── 3. Panggil Public API resmi Nextend ───────────────────────────────────
    // Signature: Project::import( $pathToFile, $groupID = 0 )
    // Return: integer slider ID kalau sukses, false kalau gagal.
    try {
        $slider_id = \Nextend\SmartSlider3\PublicApi\Project::import( $tmp_path );
    } catch ( \Throwable $e ) {
        return new WP_Error(
            'import_exception',
            'Exception saat import: ' . $e->getMessage(),
            [ 'status' => 500 ]
        );
    }

    if ( ! $slider_id ) {
        return new WP_Error(
            'import_failed',
            'Project::import() mengembalikan false. Cek WordPress debug log.',
            [ 'status' => 500 ]
        );
    }

    // ── 4. Clear cache slider ini biar frontend langsung render ───────────────
    try {
        \Nextend\SmartSlider3\PublicApi\Project::clearCache( (int) $slider_id );
    } catch ( \Throwable $e ) {
        // Non-fatal — cache akan regenerate on next render.
    }

    // ── 5. Return metadata untuk iAAWG ────────────────────────────────────────
    return new WP_REST_Response( [
        'success'   => true,
        'slider_id' => (int) $slider_id,
        'shortcode' => sprintf( '[smartslider3 slider="%d"]', (int) $slider_id ),
    ], 200 );
}
