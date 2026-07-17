<?php
/**
 * Plugin Name:  iAAWG Elementor CSS Auto-Regenerate
 * Description:  Automatically clears and regenerates Elementor CSS cache
 *               whenever a page is created or updated via the WordPress REST API.
 *               This eliminates the requirement to manually open pages in the
 *               Elementor editor after deploying via iAAWG.
 * Version:      1.0.0
 * Author:       iLogo Infralogy Indonesia
 * Requires WP:  6.0
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

/**
 * Hook fires after a page is inserted or updated via the REST API.
 * $post    WP_Post  — the page object
 * $request WP_REST_Request — the full request (lets us check it came from REST)
 * $creating bool — true on insert, false on update
 */
add_action( 'rest_after_insert_page', function ( $post, $request, $creating ) {

    // Only act when Elementor data is present in the request
    $meta = $request->get_param( 'meta' );
    if ( empty( $meta['_elementor_data'] ) ) {
        return;
    }

    // Make sure Elementor is active before calling its API
    if ( ! did_action( 'elementor/loaded' ) ) {
        return;
    }

    try {
        // Clear the per-page CSS file so Elementor regenerates it on next load
        \Elementor\Plugin::$instance->files_manager->clear_cache();

        // Also delete the specific post's cached CSS meta so it is rebuilt
        delete_post_meta( $post->ID, '_elementor_css' );

        error_log(
            sprintf(
                '[iAAWG] Elementor CSS cache cleared for page ID %d ("%s")',
                $post->ID,
                get_the_title( $post->ID )
            )
        );
    } catch ( \Exception $e ) {
        error_log( '[iAAWG] Failed to clear Elementor CSS cache: ' . $e->getMessage() );
    }

}, 10, 3 );
