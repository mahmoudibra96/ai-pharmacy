document.addEventListener('DOMContentLoaded', function() {
    console.log('JavaScript is loaded and working!');
    
    // Add a simple test function
    const shopNowBtn = document.querySelector('.btn-light');
    if(shopNowBtn) {
        shopNowBtn.addEventListener('click', function() {
            alert('Shop Now button clicked!');
        });
    }
}); 