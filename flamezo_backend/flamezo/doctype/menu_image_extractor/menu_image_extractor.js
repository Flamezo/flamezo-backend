// Copyright (c) 2025, Hetvi Patel and contributors
// For license information, please see license.txt

console.log('🎉 Menu Image Extractor JS loaded - v1.1');

frappe.ui.form.on('Menu Image Extractor', {
	refresh: function(frm) {
		console.log('📄 Menu Image Extractor form refreshed:', frm.doc.name);
		// Add custom button for extraction
		if (frm.doc.menu_images && frm.doc.menu_images.length > 0) {
			// Add extract button in the form
			if (frm.doc.extraction_status != 'Processing') {
				frm.add_custom_button(__('Extract Menu Data'), function() {
					console.log('🔘 Extract Menu Data button clicked!');
					extract_menu_data(frm);
				}).addClass('btn-primary');
			}
		}
		
		// Show status indicator
		if (frm.doc.extraction_status) {
			update_status_indicator(frm);
		}
		
		// Add button to view created items
		if (frm.doc.extraction_status == 'Completed' && frm.doc.items_created > 0) {
			frm.add_custom_button(__('View Created Products'), function() {
				frappe.set_route('List', 'Menu Product', {
					'creation': ['>=', frappe.datetime.add_days(frm.doc.extraction_date, -1)]
				});
			});
		}
		
		// Add button to view created categories
		if (frm.doc.extraction_status == 'Completed' && frm.doc.categories_created > 0) {
			frm.add_custom_button(__('View Created Categories'), function() {
				frappe.set_route('List', 'Menu Category');
			});
		}
		
		// Add approve button when status is Pending Approval
		if (frm.doc.extraction_status == 'Pending Approval') {
			frm.add_custom_button(__('Approve and Create Menu Items'), function() {
				approve_extracted_data(frm);
			}).addClass('btn-primary');
		}
		
		// Add generate recommendations button when status is Completed
		if (frm.doc.extraction_status == 'Completed') {
			frm.add_custom_button(__('Generate Recommendations'), function() {
				generate_recommendations(frm);
			}).addClass('btn-primary');
		}
	},
	
	extract_button: function(frm) {
		extract_menu_data(frm);
	},
	
	approve_button: function(frm) {
		approve_extracted_data(frm);
	},
	
	generate_recommendations_button: function(frm) {
		generate_recommendations(frm);
	},
	
	menu_images_add: function(frm) {
		// Validate image count
		if (frm.doc.menu_images && frm.doc.menu_images.length > 20) {
			frappe.msgprint({
				title: __('Maximum Images Exceeded'),
				message: __('Maximum 20 images allowed. Please remove excess images.'),
				indicator: 'red'
			});
		}
	}
});

function extract_menu_data(frm) {
	console.log('🔍 extract_menu_data function called');
	console.log('  Document:', frm.doc.name);
	console.log('  Images count:', frm.doc.menu_images ? frm.doc.menu_images.length : 0);
	
	// Validate images
	if (!frm.doc.menu_images || frm.doc.menu_images.length == 0) {
		console.log('❌ Validation failed: No images');
		frappe.msgprint({
			title: __('No Images'),
			message: __('Please upload at least one menu image before extraction.'),
			indicator: 'red'
		});
		return;
	}
	
	if (frm.doc.menu_images.length > 20) {
		console.log('❌ Validation failed: Too many images');
		frappe.msgprint({
			title: __('Too Many Images'),
			message: __('Maximum 20 images allowed. Currently {0} images uploaded.', [frm.doc.menu_images.length]),
			indicator: 'red'
		});
		return;
	}
	
	console.log('✅ Validation passed, showing confirmation dialog');
	
	// Confirm extraction
	frappe.confirm(
		__('This will extract menu data from {0} image(s) and create/update categories and products. Continue?', 
		   [frm.doc.menu_images.length]),
		function() {
			console.log('✅ User clicked YES on confirmation dialog');
			
			// Function to proceed with extraction
			const proceed_with_extraction = () => {
				console.log('✅ Proceeding with extraction');
				
				// Calculate estimated time based on number of images (roughly 3-5 minutes per image)
				const imageCount = frm.doc.menu_images.length;
				const estimatedMinutes = Math.max(5, Math.min(60, imageCount * 3)); // 3 min per image, max 60 min
				const estimatedSeconds = estimatedMinutes * 60;
				
				// Track start time and progress
				const startTime = Date.now();
				let progressValue = 0;
				let progressInterval = null;
				
				// Show progress dialog with initial message
				frappe.show_progress(__('Extracting Menu Data'), progressValue, 100, 
					__('Initializing extraction... Processing {0} image(s). This may take up to {1} minutes.', [imageCount, estimatedMinutes]));
				
				// Progress update interval - update every 10 seconds
				// Progress will go from 0% to 90% over estimated time, then jump to 100% on completion
				progressInterval = setInterval(() => {
					// Calculate progress based on elapsed time (up to 90%)
					const elapsed = (Date.now() - startTime) / 1000; // seconds
					const progressPercent = Math.min(90, (elapsed / estimatedSeconds) * 90);
					
					// Update progress with appropriate message
					let message = '';
					if (progressPercent < 10) {
						message = __('Uploading images to API...');
					} else if (progressPercent < 30) {
						message = __('Analyzing menu images with AI...');
					} else if (progressPercent < 60) {
						message = __('Extracting menu items and categories...');
					} else if (progressPercent < 85) {
						message = __('Processing and formatting data...');
					} else {
						message = __('Finalizing extraction...');
					}
					
					progressValue = Math.floor(progressPercent);
					frappe.show_progress(__('Extracting Menu Data'), progressValue, 100, message);
				}, 10000); // Update every 10 seconds
				
				// Call the extraction method
				console.log('🚀 Starting menu extraction for document:', frm.doc.name);
				console.log('📸 Images to extract:', imageCount);
				console.log('⏱️ Estimated time: ~' + estimatedMinutes + ' minutes');
				console.log('📞 Calling server method: flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.extract_menu_data');
				
				frappe.call({
					method: 'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.extract_menu_data',
					args: {
						docname: frm.doc.name
					},
					freeze: true,
					freeze_message: __('Starting extraction... Please wait.'),
					// NO TIMEOUT - function returns immediately after queuing
					callback: function(r) {
						console.log('📥 Extraction API Response:', r);
						clearInterval(progressInterval); // Stop progress updates
						
						if (r.message && r.message.success) {
							// Check if extraction was queued (background job) or completed immediately
							if (r.message.status === 'queued') {
								// Background job was queued
								frappe.hide_progress();
								
								// Show success message with batch info
								if (r.message.total_batches) {
									frappe.show_alert({
										message: __('Extraction started! Processing {0} images in {1} batch(es).').format(
											r.message.total_images || '?',
											r.message.total_batches
										),
										indicator: 'blue'
									}, 10);
								} else {
									frappe.show_alert({
										message: __(r.message.message || 'Extraction started in the background.'),
										indicator: 'blue'
									}, 10);
								}
								
								// Reload document to show "Processing" status and batch info
								frm.reload_doc();
								
								// Start enhanced progress and polling (with batch tracking)
								startEnhancedProgressAndPolling(frm);
								
							} else {
								// Immediate completion (shouldn't happen with background jobs, but handle it)
								frappe.show_progress(__('Extracting Menu Data'), 100, 100, __('Extraction completed!'));
								setTimeout(() => frappe.hide_progress(), 500);
								
								console.log('✅ Extraction successful!');
								console.log('📊 Stats:', r.message.stats);
								
								// Log extracted data preview
								if (r.message.extracted_data_preview) {
									console.log('\n📋 Extracted Data Preview:');
									console.log('  Categories found:', r.message.extracted_data_preview.categories_count);
									console.log('  Dishes found:', r.message.extracted_data_preview.dishes_count);
								}
								
								frappe.show_alert({
									message: __(r.message.message),
									indicator: 'green'
								}, 10);
								
								// Show message about review
								frappe.msgprint({
									title: __('Extraction Completed'),
									message: __('Extraction completed successfully!<br><br>Please review the extracted data below and click "Approve and Create Menu Items" to add them to the database.'),
									indicator: 'green'
								});
								
								// Reload the form to show the HTML report
								frm.reload_doc();
								
								// Force refresh of the HTML field after a short delay
								setTimeout(function() {
									if (frm.doc.extracted_data_report) {
										frm.refresh_field('extracted_data_report');
									}
								}, 500);
							}
						} else {
							console.error('❌ Extraction failed - no success in response');
							console.log('Response message:', r.message);
						}
					},
					error: function(r) {
						console.error('❌ Extraction API call failed:', r);
						if (progressInterval) {
							clearInterval(progressInterval); // Stop progress updates on error
						}
						
						// Check if job was actually queued despite timeout
						const checkJobStatus = () => {
							frappe.call({
								method: 'frappe.client.get',
								args: {
									doctype: 'Menu Image Extractor',
									name: frm.doc.name
								},
								callback: function(checkR) {
									if (checkR && checkR.message) {
										const doc = checkR.message;
										if (doc.extraction_status === 'Processing') {
											// Job was actually queued, just the response timed out
											frappe.hide_progress();
											frappe.show_alert({
												message: __('Extraction started in the background. The request timed out, but extraction is processing. Please refresh the page to check status.'),
												indicator: 'blue'
											}, 15);
											frm.reload_doc();
											// Start enhanced progress and polling
											startEnhancedProgressAndPolling(frm);
											return;
										}
									}
									
									// Job wasn't queued - show error
									frappe.hide_progress();
									
									// Determine error message based on response
									let errorMessage = __('An error occurred during extraction. Please check the extraction log for details.');
									let errorTitle = __('Extraction Failed');
									
									// Handle different error scenarios
									if (!r || (r && r.status === 0)) {
										// No response object (network error, timeout, etc.)
										errorMessage = __('Request Timed Out: The extraction request timed out before it could start. Please try again with fewer images or check your network connection.');
										errorTitle = __('Request Timed Out');
									} else {
										// Check for HTTP status codes
										const statusCode = r.status || (r.xhr && r.xhr.status);
										if (statusCode === 504 || statusCode === 408) {
											errorMessage = __('Gateway Timeout: The extraction request timed out at the server. The extraction may still be processing. Please wait a few minutes and refresh the document to check the status.');
											errorTitle = __('Request Timed Out');
										} else if (statusCode === 500) {
											errorMessage = __('Server Error: An error occurred on the server during extraction. Please check the extraction log for details.');
										} else {
											// Try to extract error message from response
											let errorMsgStr = '';
											if (r.message) {
												errorMsgStr = typeof r.message === 'string' ? r.message : JSON.stringify(r.message);
											} else if (r.error && r.error.message) {
												errorMsgStr = typeof r.error.message === 'string' ? r.error.message : JSON.stringify(r.error.message);
											} else if (r._server_messages) {
												try {
													const messages = JSON.parse(r._server_messages);
													if (messages && messages.length > 0) {
														const msg = JSON.parse(messages[0]);
														errorMsgStr = msg.message || msg.exc || '';
													}
												} catch (e) {
													console.error('Error parsing server messages:', e);
												}
											}
											
											if (errorMsgStr && errorMsgStr.includes('Timeout')) {
												errorMessage = __('Request Timeout: The extraction took longer than expected. Please try with fewer images or check your network connection.');
												errorTitle = __('Request Timed Out');
											} else if (errorMsgStr) {
												errorMessage = errorMsgStr.length > 200 ? errorMsgStr.substring(0, 200) + '...' : errorMsgStr;
											}
										}
									}
									
									frappe.msgprint({
										title: errorTitle,
										message: errorMessage,
										indicator: 'red'
									});
								}
							});
						};
						
						// Check job status immediately
						checkJobStatus();
						
						// Reload document to check if extraction status changed
						frm.reload_doc();
					}
				});
			};
			
			// Check if document has unsaved changes
			if (frm.doc.__unsaved || frm.is_dirty()) {
				console.log('💾 Document has changes, saving first...');
				frm.save().then(() => {
					console.log('✅ Document saved successfully');
					proceed_with_extraction();
				}).catch(err => {
					console.error('❌ Document save failed:', err);
					frappe.msgprint({
						title: __('Save Failed'),
						message: __('Could not save document. Please try again.'),
						indicator: 'red'
					});
				});
			} else {
				console.log('ℹ️  Document already saved, proceeding directly');
				proceed_with_extraction();
			}
		},
		function() {
			console.log('❌ User clicked NO/Cancel on confirmation dialog');
		}
	);
}

function startEnhancedProgressAndPolling(frm) {
	// Start enhanced progress bar for queued job with batch tracking
	let progressPercent = 0;
	let progressMessage = __('Extraction queued and starting...');
	const progressUpdateInterval = setInterval(() => {
		// Calculate progress based on batches if available
		if (frm.doc.total_batches && frm.doc.total_batches > 0) {
			const batchProgress = (frm.doc.completed_batches || 0) / frm.doc.total_batches * 100;
			progressPercent = Math.min(batchProgress, 95);
			progressMessage = __('Processing batches... {0}/{1} completed').format(
				frm.doc.completed_batches || 0,
				frm.doc.total_batches
			);
		} else {
			// Fallback: gradual progress if batch info not available
			progressPercent = Math.min(progressPercent + 0.5, 95);
			
			// Update message based on progress
			if (progressPercent < 10) {
				progressMessage = __('Initializing extraction...');
			} else if (progressPercent < 30) {
				progressMessage = __('Uploading images to API...');
			} else if (progressPercent < 60) {
				progressMessage = __('Analyzing menu images with AI...');
			} else if (progressPercent < 85) {
				progressMessage = __('Processing extracted data...');
			} else {
				progressMessage = __('Finalizing extraction...');
			}
		}
		
		frappe.show_progress(__('Extracting Menu Data'), Math.floor(progressPercent), 100, progressMessage);
	}, 5000); // Update every 5 seconds
	
	// Start polling for status updates
	let pollCount = 0;
	const maxPolls = 120; // Poll for up to 20 minutes (120 * 10 seconds)
	const pollInterval = setInterval(() => {
		pollCount++;
		frm.reload_doc();
		
		// Stop polling if status changed from Processing
		if (frm.doc.extraction_status !== 'Processing') {
			clearInterval(pollInterval);
			clearInterval(progressUpdateInterval);
			frappe.hide_progress();
			
			if (frm.doc.extraction_status === 'Pending Approval') {
				frappe.show_progress(__('Extraction completed!'), 100, 100, __('Review and approve the extracted data.'));
				setTimeout(() => frappe.hide_progress(), 2000);
				frappe.show_alert({
					message: __('Extraction completed! Please review and approve the data.'),
					indicator: 'green'
				}, 10);
			} else if (frm.doc.extraction_status === 'Failed') {
				frappe.hide_progress();
				frappe.show_alert({
					message: __('Extraction failed. Please check the extraction log for details.'),
					indicator: 'red'
				}, 10);
			}
		} else if (pollCount >= maxPolls) {
			clearInterval(pollInterval);
			clearInterval(progressUpdateInterval);
			frappe.hide_progress();
			frappe.show_alert({
				message: __('Extraction is taking longer than expected. Please check back later.'),
				indicator: 'orange'
			}, 10);
		}
	}, 10000); // Poll every 10 seconds
}

function approve_extracted_data(frm) {
	console.log('🔍 approve_extracted_data function called');
	console.log('  Document:', frm.doc.name);
	
	// Validate that there's data to approve
	if (!frm.doc.extracted_categories || frm.doc.extracted_categories.length == 0) {
		if (!frm.doc.extracted_dishes || frm.doc.extracted_dishes.length == 0) {
			frappe.msgprint({
				title: __('No Data to Approve'),
				message: __('No extracted data found. Please extract menu data first.'),
				indicator: 'red'
			});
			return;
		}
	}
	
	// Count items
	const dishes_count = frm.doc.extracted_dishes ? frm.doc.extracted_dishes.length : 0;
	
	// Confirm approval
	frappe.confirm(
		__('This will create/update {0} dishes in the database. Continue?', 
		   [dishes_count]),
		function() {
			console.log('✅ User confirmed approval');
			
			// Call the approval method
			frappe.call({
				method: 'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.approve_extracted_data',
				args: {
					docname: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Approving and creating menu items...'),
				callback: function(r) {
					console.log('📥 Approval API Response:', r);
					
					if (r.message && r.message.success) {
						console.log('✅ Approval successful!');
						console.log('📊 Stats:', r.message.stats);
						
						// Reload the form first to get updated data
						frm.reload_doc();
						
						// Show alert (non-blocking)
						frappe.show_alert({
							message: __(r.message.message),
							indicator: 'green'
						}, 5);
						
						// Show detailed stats in a non-blocking way after a short delay
						if (r.message.stats) {
							setTimeout(function() {
								frappe.msgprint({
									title: __('Approval Completed'),
									message: __('Categories created: {0}<br>Items created: {1}<br>Items updated: {2}<br>Items skipped: {3}', 
										[r.message.stats.categories_created, 
										 r.message.stats.items_created,
										 r.message.stats.items_updated,
										 r.message.stats.items_skipped]),
									indicator: 'green'
								});
							}, 500);
						}
					} else {
						console.error('❌ Approval failed');
						frappe.msgprint({
							title: __('Approval Failed'),
							message: __('An error occurred during approval. Please check the extraction log for details.'),
							indicator: 'red'
						});
						frm.reload_doc();
					}
				},
				error: function(r) {
					console.error('❌ Approval API call failed:', r);
					frappe.msgprint({
						title: __('Approval Failed'),
						message: __('An error occurred during approval. Please check the extraction log for details.'),
						indicator: 'red'
					});
					frm.reload_doc();
				}
			});
		},
		function() {
			console.log('❌ User cancelled approval');
		}
	);
}

function update_status_indicator(frm) {
	let status = frm.doc.extraction_status;
	let color = 'blue';
	
	if (status == 'Completed') {
		color = 'green';
	} else if (status == 'Failed') {
		color = 'red';
	} else if (status == 'Processing') {
		color = 'orange';
	} else if (status == 'Pending Approval') {
		color = 'yellow';
	}
	
	frm.dashboard.add_indicator(__('Status: {0}', [status]), color);
}

function generate_recommendations(frm) {
	console.log('🔍 generate_recommendations function called');
	console.log('  Document:', frm.doc.name);
	
	// Validate status
	if (frm.doc.extraction_status != 'Completed') {
		frappe.msgprint({
			title: __('Cannot Generate Recommendations'),
			message: __('Recommendations can only be generated after extraction is completed.'),
			indicator: 'red'
		});
		return;
	}
	
	// Confirm generation
	frappe.confirm(
		__('This will generate AI recommendations for all products of this restaurant. This may take a few minutes. Continue?'),
		function() {
			console.log('✅ User confirmed recommendations generation');
			
			// Call the generation method
			frappe.call({
				method: 'flamezo_backend.flamezo.doctype.menu_image_extractor.menu_image_extractor.generate_recommendations',
				args: {
					docname: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Generating recommendations... This may take a few minutes.'),
				callback: function(r) {
					console.log('📥 Recommendations API Response:', r);
					
					if (r.message && r.message.success) {
						console.log('✅ Recommendations generation successful!');
						
						// Reload the form
						frm.reload_doc();
						
						// Show alert
						frappe.show_alert({
							message: __(r.message.message),
							indicator: 'green'
						}, 5);
						
						// Show detailed message
						setTimeout(function() {
							frappe.msgprint({
								title: __('Recommendations Generated'),
								message: __('Successfully generated recommendations for {0} out of {1} products.', 
									[r.message.updated_count || 0, r.message.total_products || 0]),
								indicator: 'green'
							});
						}, 500);
					} else {
						console.error('❌ Recommendations generation failed');
						frappe.msgprint({
							title: __('Generation Failed'),
							message: __('An error occurred during recommendations generation. Please check the extraction log for details.'),
							indicator: 'red'
						});
						frm.reload_doc();
					}
				},
				error: function(r) {
					console.error('❌ Recommendations API call failed:', r);
					frappe.msgprint({
						title: __('Generation Failed'),
						message: __('An error occurred during recommendations generation. Please check the extraction log for details.'),
						indicator: 'red'
					});
					frm.reload_doc();
				}
			});
		},
		function() {
			console.log('❌ User cancelled recommendations generation');
		}
	);
}

