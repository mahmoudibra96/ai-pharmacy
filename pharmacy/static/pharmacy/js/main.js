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

function requestStock(medicineName) {
    alert(`Stock request for ${medicineName} has been noted. We'll notify when available.`);
    // You can implement actual stock request functionality here
} 