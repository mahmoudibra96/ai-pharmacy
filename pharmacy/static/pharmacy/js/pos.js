$(document).ready(function() {
    // Initialize Select2 for customer search
    $('#customer-select').select2({
        placeholder: 'Search customer by name or phone...',
        allowClear: true,
        ajax: {
            url: '{% url "pharmacy:customer_search" %}',
            dataType: 'json',
            delay: 250,
            data: function(params) {
                return {
                    term: params.term
                };
            },
            processResults: function(data) {
                return {
                    results: data.results.map(function(item) {
                        return {
                            id: item.id,
                            text: item.text + ' - Points: ' + item.points
                        };
                    })
                };
            },
            cache: true
        }
    });

    // Update hidden input when customer is selected
    $('#customer-select').on('select2:select', function(e) {
        $('#selected-customer-id').val(e.params.data.id);
    });

    // Clear customer ID when customer is removed
    $('#customer-select').on('select2:unselect', function() {
        $('#selected-customer-id').val('');
    });
}); 