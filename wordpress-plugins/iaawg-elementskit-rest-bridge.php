<?php
/**
 * Plugin Name: iAAWG – ElementsKit REST Bridge
 * Description: (1) Exposes the elementskit_template CPT and its meta fields
 *              to the WordPress REST API so iAAWG can deploy global
 *              header/footer templates via create_elementskit_template().
 *              (2) Auto-activates newly created H/F templates by writing
 *              them into ElementsKit's own render registry (wp_options),
 *              which is the step normally done manually through the
 *              ElementsKit admin UI.
 * Version:     1.1.0
 * Author:      iAAWG / iLogo Infralogy Indonesia
 *
 * INSTALLATION:
 *   1. Buat folder: wp-content/plugins/iaawg-elementskit-rest-bridge/
 *   2. Letakkan file ini di dalamnya.
 *   3. Aktifkan dari WordPress Admin → Plugins.
 *
 * REQUIRES: ElementsKit Elementor Addons (free) sudah aktif terlebih dahulu.
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}


// ─────────────────────────────────────────────────────────────────────────────
// Part 1 — Make elementskit_template CPT accessible via REST API
// ─────────────────────────────────────────────────────────────────────────────

/**
 * ElementsKit registers elementskit_template with show_in_rest = false.
 * We override that at priority 20 (after ElementsKit runs at 10).
 */
add_filter( 'register_post_type_args', function ( $args, $post_type ) {
    if ( $post_type === 'elementskit_template' ) {
        $args['show_in_rest'] = true;
        $args['rest_base']    = 'elementskit_template';
    }
    return $args;
}, 20, 2 );


/**
 * Register all meta fields needed by iAAWG for REST write access.
 * Without explicit registration, POSTed meta values are silently ignored.
 */
add_action( 'init', function () {

    $fields = [
        '_elementskit_template_type' => 'ElementsKit template type: "header" or "footer".',
        '_elementskit_conditions'    => 'ElementsKit display conditions (JSON string).',
        '_elementor_data'            => 'Elementor page builder JSON data.',
        '_elementor_edit_mode'       => 'Elementor edit mode flag.',
        '_elementor_template_type'   => 'Elementor template type.',
        '_elementor_version'         => 'Elementor version.',
    ];

    foreach ( $fields as $key => $description ) {
        register_post_meta( 'elementskit_template', $key, [
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


// ─────────────────────────────────────────────────────────────────────────────
// Part 2 — Auto-activate H/F templates after REST API creation
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fires after a elementskit_template post is inserted or updated via REST API.
 *
 * ElementsKit's render engine reads its active H/F templates from a
 * wp_options entry called 'elementskit_header_footer_data'.
 * Creating the CPT post alone doesn't update this option — that normally
 * happens through the ElementsKit admin UI "Save" button.
 * This hook replicates that save automatically.
 *
 * The option format ElementsKit expects (array keyed by post ID):
 *   [
 *     903 => [
 *       'id'         => 903,
 *       'type'       => 'header',   // or 'footer'
 *       'conditions' => [           // decoded from _elementskit_conditions
 *         ['id' => 'general', 'rule' => 'show', 'isSelected' => true]
 *       ],
 *     ],
 *     ...
 *   ]
 */
add_action( 'rest_after_insert_elementskit_template', function ( WP_Post $post ) {

    $post_id = $post->ID;

    // Read meta written by iAAWG's REST call
    $hf_type    = get_post_meta( $post_id, '_elementskit_template_type', true );
    $conditions_raw = get_post_meta( $post_id, '_elementskit_conditions', true );

    // Only process header / footer templates
    if ( ! in_array( $hf_type, [ 'header', 'footer' ], true ) ) {
        return;
    }

    // Decode conditions — fall back to "entire site" if missing / malformed
    $conditions = [];
    if ( $conditions_raw ) {
        $decoded = json_decode( $conditions_raw, true );
        if ( is_array( $decoded ) ) {
            $conditions = $decoded;
        }
    }
    if ( empty( $conditions ) ) {
        $conditions = [ [ 'id' => 'general', 'rule' => 'show', 'isSelected' => true ] ];
    }

    // Load existing registry and add / update this template
    $registry = get_option( 'elementskit_header_footer_data', [] );
    if ( ! is_array( $registry ) ) {
        $registry = [];
    }

    $registry[ $post_id ] = [
        'id'         => $post_id,
        'type'       => $hf_type,
        'conditions' => $conditions,
    ];

    update_option( 'elementskit_header_footer_data', $registry );

    // Clear Elementor's CSS cache for this template so styles render immediately
    // (mirrors what iaawg-elementor-css-regen.php does for regular pages)
    if ( class_exists( '\Elementor\Plugin' ) ) {
        \Elementor\Plugin::$instance->files_manager->clear_cache();
    }

    error_log( "[iAAWG REST Bridge] Auto-activated ElementsKit {$hf_type} template (ID: {$post_id})" );

}, 10, 1 );


// ─────────────────────────────────────────────────────────────────────────────
// Part 3 — Cleanup: remove deactivated / deleted templates from registry
// ─────────────────────────────────────────────────────────────────────────────

/**
 * When an elementskit_template post is trashed or deleted,
 * remove it from the registry so it stops rendering.
 */
add_action( 'trashed_post', 'iaawg_ekbridge_remove_from_registry' );
add_action( 'deleted_post', 'iaawg_ekbridge_remove_from_registry' );

function iaawg_ekbridge_remove_from_registry( int $post_id ) {
    if ( get_post_type( $post_id ) !== 'elementskit_template' ) {
        return;
    }
    $registry = get_option( 'elementskit_header_footer_data', [] );
    if ( isset( $registry[ $post_id ] ) ) {
        unset( $registry[ $post_id ] );
        update_option( 'elementskit_header_footer_data', $registry );
    }
}
