import React from 'react';

const VideoPlayer = ({ src }) => {
  if (!src) return null;

  return (
    <div className="w-full max-w-[270px] mx-auto"> {/* 270px is 9:16 ratio for a 480px height */}
      <div className="relative w-full aspect-[9/16]">
        <video 
          src={src} 
          controls 
          className="absolute top-0 left-0 w-full h-full rounded-lg object-cover"
        >
        </video>
      </div>
    </div>
  );
};

export default VideoPlayer;
